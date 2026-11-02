"""Install, update or remove the codex-tuning rules and hooks in a Codex home directory.

The repository is the source of truth. The installer replaces only its own
marked block in AGENTS.md and only its own entries in hooks.json, copies the
hook scripts, and backs up every file it changes. Running it again is safe.

Usage:
    python install.py [--dry-run] [--uninstall] [--codex-home PATH] [--python CMD]
"""

import argparse
import difflib
import json
import os
import shutil
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
SOURCE_BLOCK = REPO / "global" / "AGENTS.md"
SOURCE_HOOKS = REPO / "global" / "hooks"
SCRIPTS = ("style_guard.py", "style_reminder.py")
BLOCK_START = "<!-- engineering-style:start"
BLOCK_END = "<!-- engineering-style:end -->"
# Event -> (script, timeout in seconds). Keep the generated command text stable:
# Codex asks for approval again whenever an approved hook definition changes.
HOOKS = {"UserPromptSubmit": ("style_reminder.py", 10), "Stop": ("style_guard.py", 30)}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--python", default="python -X utf8" if os.name == "nt" else "python3 -X utf8",
                        help="command prefix used to run the hook scripts")
    parser.add_argument("--dry-run", action="store_true", help="show the changes without writing them")
    parser.add_argument("--uninstall", action="store_true", help="remove the managed block, hooks and scripts")
    return parser.parse_args()


def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def render_agents(text, block):
    """Return AGENTS.md with the managed block replaced, appended, or removed when block is None."""
    start = text.find(BLOCK_START)
    if start < 0:
        head, tail = text, ""
    else:
        end = text.find(BLOCK_END, start)
        if end < 0:
            raise SystemExit(f"AGENTS.md contains '{BLOCK_START}' without '{BLOCK_END}'; fix it by hand first.")
        head, tail = text[:start], text[end + len(BLOCK_END):]
    parts = [part for part in (head.strip("\n"), block, tail.strip("\n")) if part]
    return "\n\n".join(parts) + "\n" if parts else ""


def owns(group, script):
    return any(script in hook.get("command", "") for hook in group.get("hooks", []))


def merge_groups(groups, script, entry):
    """Replace this project's hook group in place, so other groups keep their positions."""
    result, placed = [], False
    for group in groups:
        if not owns(group, script):
            result.append(group)
        elif entry and not placed:
            result.append(entry)
            placed = True
    if entry and not placed:
        result.append(entry)
    return result


def render_hooks(text, hooks_dir, python, install):
    config = json.loads(text) if text.strip() else {}
    events = config.setdefault("hooks", {})
    for event, (script, timeout) in HOOKS.items():
        command = f"{python} {(hooks_dir / script).as_posix()}"
        entry = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]} if install else None
        groups = merge_groups(events.get(event, []), script, entry)
        if groups:
            events[event] = groups
        else:
            events.pop(event, None)
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def plan(args, home):
    """Return {target path: new text, or None to delete} for every file that would change."""
    hooks_dir = home / "hooks"
    block = None if args.uninstall else read(SOURCE_BLOCK).strip()
    targets = {
        home / "AGENTS.md": render_agents(read(home / "AGENTS.md"), block),
        home / "hooks.json": render_hooks(read(home / "hooks.json"), hooks_dir, args.python, not args.uninstall),
    }
    for name in SCRIPTS:
        targets[hooks_dir / name] = None if args.uninstall else read(SOURCE_HOOKS / name)
    return {path: text for path, text in targets.items() if text != (read(path) if path.exists() else None)}


def show(changes, home):
    if not changes:
        print("已是最新，无需改动。")
        return
    for path, text in changes.items():
        rel = path.relative_to(home).as_posix()
        if text is None:
            print(f"删除 {rel}")
            continue
        print(f"{'更新' if path.exists() else '新建'} {rel}")
        if path.suffix in (".md", ".json"):
            diff = difflib.unified_diff(read(path).splitlines(), text.splitlines(), f"a/{rel}", f"b/{rel}",
                                        lineterm="")
            print("\n".join(diff))


def apply(changes, home):
    stamp = home / "backups" / time.strftime("codex-tuning-%Y%m%d-%H%M%S")
    backup, n = stamp, 1
    while backup.exists():
        backup, n = stamp.with_name(f"{stamp.name}-{n}"), n + 1
    for path, text in changes.items():
        if path.exists():
            target = backup / path.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if text is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
    if backup.exists():
        print(f"原文件已备份到 {backup}")


def main():
    args = parse_args()
    home = args.codex_home.resolve()
    changes = plan(args, home)
    show(changes, home)
    if changes and not args.dry_run:
        apply(changes, home)
        print("完成。如果 hooks.json 中的命令有变化，请在 Codex 中运行 /hooks 重新批准。")


if __name__ == "__main__":
    main()
