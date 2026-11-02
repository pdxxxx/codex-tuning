"""UserPromptSubmit hook: re-inject a short engineering-style digest every turn.

The full rules live in ~/.codex/AGENTS.md. This digest survives context
compaction and stays near the model's attention in long sessions. A repository
whose .codex-style.json sets "enabled": false gets no digest.
"""

import json
import os
import sys

from style_guard import find_config

DIGEST = (
    "[engineering-style] 遵守 ~/.codex/AGENTS.md：只在系统边界校验，不为不可能的状态加防御代码；测试只覆盖需求行为和真实 bug，量与改动相当；"
    "只用已有领域词；不新增非必要的包、文档、计划或日志文件；新写或修改的函数≤80行、行≤120字符，不为此改动旧代码；测试按行为命名；"
    "注释、spec、文案写完整自然的句子，spec 只写当前状态；先拿证据再下结论；安装依赖不改写锁文件。"
)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not find_config(payload.get("cwd") or os.getcwd())["enabled"]:
        return
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": DIGEST},
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
