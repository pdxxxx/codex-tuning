"""Survey a repository for maintainability problems common in agent-written code.

Read-only. Prints a Markdown report covering size by directory, the longest
functions, long lines, naming smells, jargon frequency, documentation volume
and commit size. Only tracked files are read.

Usage:
    python tools/audit_repo.py [REPO] [--depth 3] [--limit 15] [--terms WORD ...]
"""

import argparse
import ast
import re
import subprocess
from collections import Counter
from pathlib import Path

CODE_EXTS = {".go", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".rs", ".java", ".kt", ".cs"}
MAX_FILE_BYTES = 1024 * 1024
MAX_FUNC_LINES = 80
MAX_LINE_CHARS = 120
TEST_FILE = re.compile(r"(_test\.(go|py)|\.(test|spec)\.[cm]?[jt]sx?)$|(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$")
DEFAULT_TERMS = ["exact", "proof", "prove", "fence", "lineage", "authority", "permit", "generation",
                 "supersede", "native", "legacy", "original", "conservative", "canonical"]
SMELLS = [
    (re.compile(r"(review|audit|regression|round\d*)[^/]*(_test\.(go|py)|\.test\.[jt]sx?)$"), "按审查轮次命名的测试文件"),
    (re.compile(r"(^|/)docs?/[^/]*\d{4}-\d{2}-\d{2}[^/]*\.md$"), "按日期命名的流水账文档"),
    (re.compile(r"(plan|checkpoint|progress)[^/]*\.md$", re.I), "计划或进度类文档"),
    (re.compile(r"\.(log|exe|dll|so|dylib|zip|tar\.gz)$"), "日志、二进制或压缩包"),
]
GO_FUNC = re.compile(r"^func (\([^)]*\) )?(\w+)")
COMMENT = re.compile(r"^\s*(//|#|/?\*)")
# Tool-managed dot directories (agent skills, workflow scripts), except project specs.
TOOL_DIR = re.compile(r"^\.(?!trellis/spec/)")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--depth", type=int, default=3, help="directory depth for the size table")
    parser.add_argument("--limit", type=int, default=15, help="rows per table")
    parser.add_argument("--terms", nargs="+", default=DEFAULT_TERMS, help="words to count in comments and docs")
    return parser.parse_args()


def git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.stdout if result.returncode == 0 else ""


def is_code(path):
    return Path(path).suffix.lower() in CODE_EXTS


def is_test(path):
    return bool(TEST_FILE.search(path))


def table(header, rows):
    if not rows:
        return ["（无）"]
    return ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header), *rows]


def load_sources(repo, files):
    sources = {}
    for path in files:
        full = repo / path
        if (is_code(path) or path.endswith(".md")) and full.is_file() and full.stat().st_size <= MAX_FILE_BYTES:
            sources[path] = full.read_text(encoding="utf-8", errors="replace")
    return sources


def size_section(sources, depth, limit):
    code, tests = Counter(), Counter()
    for path, text in sources.items():
        if is_code(path):
            directory = "/".join(path.split("/")[:-1][:depth]) or "."
            (tests if is_test(path) else code)[directory] += text.count("\n")
    rows = [f"| `{d}` | {n} | {tests[d]} |" for d, n in code.most_common(limit)]
    return ["## 规模", "", f"非测试代码 {sum(code.values())} 行，测试代码 {sum(tests.values())} 行。"
            f"非测试代码最多的 {limit} 个目录：", "", *table(["目录", "非测试", "测试"], rows)]


def go_functions(text):
    name, start = None, 0
    for i, line in enumerate(text.splitlines()):
        match = GO_FUNC.match(line)
        if match and not line.rstrip().endswith("}"):
            name, start = (match.group(1) or "") + match.group(2), i
        elif name and line == "}":
            yield name, i - start + 1
            name = None


def py_functions(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node.end_lineno - node.lineno + 1


def functions_section(sources, limit):
    found = []
    for path, text in sources.items():
        measure = {".go": go_functions, ".py": py_functions}.get(Path(path).suffix)
        if measure and not is_test(path):
            found += [(length, path, name) for name, length in measure(text) if length > MAX_FUNC_LINES]
    found.sort(reverse=True)
    rows = [f"| {length} | `{path}` | `{name}` |" for length, path, name in found[:limit]]
    return ["## 超长函数", "", f"Go 和 Python 非测试代码中超过 {MAX_FUNC_LINES} 行的函数共 {len(found)} 个；"
            "其他语言请用对应的 linter（例如 ESLint 的 max-lines-per-function）。", "",
            *table(["行数", "文件", "函数"], rows)]


def long_lines_section(sources):
    counts = Counter()
    for path, text in sources.items():
        if is_code(path) and not is_test(path):
            counts[Path(path).suffix] += sum(len(line.expandtabs(4)) > MAX_LINE_CHARS for line in text.splitlines())
    rows = [f"| `{ext}` | {n} |" for ext, n in counts.most_common() if n]
    return ["## 超长行", "", f"非测试代码中超过 {MAX_LINE_CHARS} 字符的行（tab 按 4 列计）：", "",
            *table(["扩展名", "行数"], rows)]


def smells_section(files):
    lines = ["## 命名与仓库卫生", ""]
    for pattern, label in SMELLS:
        hits = [path for path in files if pattern.search(path)]
        examples = "，例如 " + "、".join(f"`{path}`" for path in hits[:5]) if hits else ""
        lines.append(f"- {label}：{len(hits)} 个{examples}")
    return lines


def terms_section(sources, terms):
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, terms)) + r")\w*", re.I)
    counts = Counter()
    for path, text in sources.items():
        lines = text.splitlines() if path.endswith(".md") else [l for l in text.splitlines() if COMMENT.match(l)]
        for line in lines:
            counts.update(match.group(1).lower() for match in pattern.finditer(line))
    rows = [f"| {term} | {counts[term]} |" for term in sorted(terms, key=lambda t: -counts[t])]
    return ["## 概念词频率", "", "注释和 Markdown 中的出现次数。高频而又没有术语表定义的词，通常说明术语在蔓延：", "",
            *table(["词", "次数"], rows)]


def docs_section(sources):
    docs = [text for path, text in sources.items() if path.endswith(".md")]
    words = sum(len(text.split()) for text in docs)
    return ["## 文档", "", f"Markdown 文件 {len(docs)} 个，共约 {words} 词（按空白分隔计数）。"]


def commits_section(repo, limit):
    commits = []
    for line in git(repo, "log", "-n", "50", "--shortstat", "--format=@%h %s").splitlines():
        if line.startswith("@"):
            commits.append([line[1:].replace("|", "\\|"), 0, 0])
        elif "changed" in line and commits:
            stats = {kind: int(n) for n, kind in re.findall(r"(\d+) (file|insertion|deletion)", line)}
            commits[-1][1:] = [stats.get("file", 0), stats.get("insertion", 0) + stats.get("deletion", 0)]
    big = [c for c in commits if c[1] >= 50 or c[2] >= 2000]
    rows = [f"| {title} | {files} | {lines} |" for title, files, lines in big[:limit]]
    return ["## 提交粒度", "", f"最近 {len(commits)} 个提交中，{len(big)} 个改动超过 50 个文件或 2000 行：", "",
            *table(["提交", "文件", "增删行"], rows)]


def main():
    args = parse_args()
    repo = Path(args.repo).resolve()
    files = [path for path in git(repo, "ls-files").splitlines() if not TOOL_DIR.match(path)]
    if not files:
        raise SystemExit(f"{repo} 不是 git 仓库，或者没有被跟踪的文件。")
    sources = load_sources(repo, files)
    sections = [
        size_section(sources, args.depth, args.limit),
        functions_section(sources, args.limit),
        long_lines_section(sources),
        smells_section(files),
        terms_section(sources, [term.lower() for term in args.terms]),
        docs_section(sources),
        commits_section(repo, args.limit),
    ]
    print(f"# 仓库体检：{repo.name}\n")
    print("\n\n".join("\n".join(section) for section in sections))


if __name__ == "__main__":
    main()
