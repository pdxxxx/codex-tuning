"""Stop hook: check this turn's working-tree changes against the engineering style.

The hook blocks the stop once with a list of new findings, so the agent either
fixes them or explains in its final reply why they are intentional. Findings
already reported in the same session are not repeated.

Length rules apply only to new and changed code. A function that was already
over the limit is reported only when it grows substantially, so hotfixes in
legacy code stay small instead of turning into refactors.

A repository can tune or disable the checks with `.codex-style.json` at its
root, for example {"enabled": false} or {"max_func_lines": 100}.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULTS = {"enabled": True, "max_func_lines": 80, "max_line_chars": 120, "func_growth_allowance": 20}
CONFIG_NAME = ".codex-style.json"
MAX_FILE_BYTES = 512 * 1024
MAX_UNTRACKED_SCANNED = 300
MAX_SHOWN = 15

CODE_EXTS = {".go", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".rs", ".java", ".kt", ".cs"}
# Tool-managed dot directories, except project specs which agents also write.
SKIP_ROOT = re.compile(r"^\.(?!trellis/spec/)")
SKIP_PATH = re.compile(
    r"(^|/)(vendor|node_modules|testdata|dist|build|generated|i18n|locales?)(/|$)|\.min\.|_gen\.|\.pb\."
)
BAD_NAMES = [
    (re.compile(r"(review|audit)[^/]*_test\.go$|_regression_test\.go$|\.(review|audit)\.test\.[jt]sx?$"),
     "测试文件按审查轮次命名，应按被测行为命名并并入对应测试文件"),
    (re.compile(r"(^|/)docs?/[^/]*\d{4}-\d{2}-\d{2}[^/]*\.md$"),
     "按日期新增的流水账文档，发布/验证记录应写进 CHANGELOG"),
    (re.compile(r"(^|/)[^/]*(commit|work|implementation)-plan[^/]*\.md$|(^|/)[^/]*checkpoint[^/]*\.md$", re.I),
     "工作计划/进度类文件不应进入仓库"),
    (re.compile(r"\.(log|exe|dll|so|dylib)$"),
     "日志或二进制文件不应进入仓库"),
]
# A lockfile rewritten while its manifest is unchanged usually means an unintended install.
LOCKFILES = {
    "pnpm-lock.yaml": "package.json", "package-lock.json": "package.json", "yarn.lock": "package.json",
    "go.sum": "go.mod", "Cargo.lock": "Cargo.toml", "poetry.lock": "pyproject.toml", "uv.lock": "pyproject.toml",
}
GO_FUNC = re.compile(r"^func (\([^)]*\) )?(\w+)")
GLUED_DATE = re.compile(r"[A-Za-z]\d{4}-\d{2}-\d{2}")


def git(cwd, *args):
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return result.stdout if result.returncode == 0 else ""


def find_config(start):
    """Return settings from the nearest .codex-style.json, searching up to the repository root."""
    for directory in [Path(start), *Path(start).parents]:
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            try:
                return {**DEFAULTS, **json.loads(candidate.read_text(encoding="utf-8"))}
            except (OSError, ValueError):
                break
        if (directory / ".git").exists():
            break
    return dict(DEFAULTS)


def collect_changes(root):
    """Map changed paths to their git status; untracked files use "?"."""
    changes = {}
    for line in git(root, "diff", "HEAD", "--name-status", "--no-renames").splitlines():
        status, _, path = line.partition("\t")
        if status != "D":
            changes[path] = status
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    for path in untracked[:MAX_UNTRACKED_SCANNED]:
        changes[path] = "?"
    return changes


def added_lines(root, path, status):
    """Yield (line_number, text) for lines added or changed relative to HEAD."""
    if status == "?":
        try:
            text = Path(root, path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        yield from enumerate(text.splitlines(), 1)
        return
    lineno = 0
    for line in git(root, "diff", "HEAD", "-U0", "--", path).splitlines():
        hunk = re.match(r"^@@ -\S+ \+(\d+)", line)
        if hunk:
            lineno = int(hunk.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            yield lineno, line[1:]
            lineno += 1


def go_func_lengths(source):
    lengths, name, start = {}, None, 0
    for i, line in enumerate(source.splitlines()):
        match = GO_FUNC.match(line)
        if match and not line.rstrip().endswith("}"):
            name, start = (match.group(1) or "") + match.group(2), i
        elif name and line == "}":
            lengths[name] = i - start + 1
            name = None
    return lengths


def check_markdown(root, path, status, findings):
    for lineno, text in added_lines(root, path, status):
        if "supersede" in text.lower():
            findings.append(f"{path}:{lineno}: 文档写成了变更史（supersede），应直接改写为当前规则")
        if GLUED_DATE.search(text):
            findings.append(f"{path}:{lineno}: 单词和日期粘连，请写成完整句子")


def check_long_lines(root, path, status, cfg, findings):
    limit = cfg["max_line_chars"]
    long_lines = [n for n, text in added_lines(root, path, status) if len(text.expandtabs(4)) > limit]
    if long_lines:
        shown = ", ".join(map(str, long_lines[:3]))
        findings.append(f"{path}: {len(long_lines)} 行新增或修改的代码超过 {limit} 字符（如第 {shown} 行）")


def check_go_functions(root, path, status, cfg, findings):
    limit, allowance = cfg["max_func_lines"], cfg["func_growth_allowance"]
    current = go_func_lengths(Path(root, path).read_text(encoding="utf-8", errors="replace"))
    before = {} if status in ("?", "A") else go_func_lengths(git(root, "show", f"HEAD:{path}"))
    for name, length in current.items():
        old = before.get(name)
        if length <= limit:
            continue
        if old is None or old <= limit:
            findings.append(f"{path}: 函数 {name} 有 {length} 行，超过 {limit} 行，应拆分")
        elif length - old > allowance:
            findings.append(f"{path}: 函数 {name} 原本已有 {old} 行，本轮又增加 {length - old} 行；"
                            "新增逻辑应提取为独立函数")


def check_file(root, path, status, cfg, findings):
    if SKIP_ROOT.match(path):
        return
    if status in ("?", "A"):
        findings.extend(f"{path}: {message}" for pattern, message in BAD_NAMES if pattern.search(path))
    full = Path(root, path)
    if not full.is_file() or full.stat().st_size > MAX_FILE_BYTES:
        return
    ext = full.suffix.lower()
    if ext == ".md":
        check_markdown(root, path, status, findings)
    elif ext in CODE_EXTS and not SKIP_PATH.search(path):
        check_long_lines(root, path, status, cfg, findings)
        if ext == ".go" and not path.endswith("_test.go"):
            check_go_functions(root, path, status, cfg, findings)


def check_lockfiles(changes, findings):
    for path in changes:
        manifest = LOCKFILES.get(Path(path).name)
        if manifest and Path(path).with_name(manifest).as_posix() not in changes:
            findings.append(f"{path}: 锁文件被改写但 {manifest} 未改动；确认是否为意外的依赖安装，必要时还原")


def check_new_go_packages(root, changes, findings):
    new_go = [p for p, s in changes.items()
              if s in ("?", "A") and p.endswith(".go") and not p.endswith("_test.go")]
    for directory in sorted({Path(p).parent.as_posix() for p in new_go}):
        if not SKIP_ROOT.match(directory) and not git(root, "ls-tree", "--name-only", "HEAD", directory + "/"):
            findings.append(f"{directory}/: 新建了 Go 包，请确认现有包确实放不下")


def collect_findings(root, cfg):
    changes = collect_changes(root)
    findings = []
    for path, status in changes.items():
        check_file(root, path, status, cfg, findings)
    check_lockfiles(changes, findings)
    check_new_go_packages(root, changes, findings)
    return list(dict.fromkeys(findings))


def unseen(payload, findings):
    """Drop findings already reported in this session and remember the rest."""
    key = payload.get("session_id") or payload.get("transcript_path") or ""
    if not key:
        return findings
    store = Path(tempfile.gettempdir(), "codex-style-guard", hashlib.sha256(key.encode()).hexdigest()[:16] + ".json")
    try:
        seen = set(json.loads(store.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        seen = set()
    fresh = [f for f in findings if f not in seen]
    if fresh:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(sorted(seen | set(fresh)), ensure_ascii=False), encoding="utf-8")
    return fresh


def block_reason(findings):
    shown = findings[:MAX_SHOWN]
    more = f"\n…另有 {len(findings) - len(shown)} 条" if len(findings) > len(shown) else ""
    return ("工程风格检查发现以下问题（见 ~/.codex/AGENTS.md）。请修复本轮引入的问题；"
            "如果是有意为之，或属于改动前已存在的状态，在最终回复里用一句话说明即可，不必修改。"
            "长度类问题只针对本轮新写或修改的代码，不要为此改动未触及的旧代码：\n- "
            + "\n- ".join(shown) + more)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    if payload.get("stop_hook_active"):
        return
    cwd = payload.get("cwd") or os.getcwd()
    if not git(cwd, "rev-parse", "--verify", "HEAD"):
        return
    root = git(cwd, "rev-parse", "--show-toplevel").strip()
    cfg = find_config(cwd)
    if not cfg["enabled"]:
        return
    fresh = unseen(payload, collect_findings(root, cfg))
    if fresh:
        print(json.dumps({"decision": "block", "reason": block_reason(fresh)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
