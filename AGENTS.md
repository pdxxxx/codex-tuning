# codex-tuning

这个仓库维护安装到 `~/.codex` 的规则和 hook，以及配套的工具和文档。

- 修改 `global/` 后运行测试和 `python install.py --dry-run`，把对 `~/.codex` 的影响给用户看；未经确认不运行实际安装。
- hook 和工具只用 Python 标准库，兼容 3.10 以上。hook 脚本安装后独立运行，只能导入同目录的其他 hook 脚本。
- 不改变 `install.py` 生成的 hook 命令文本，除非确实需要；命令变化会让用户在 Codex 中重新批准 hook。
- 规则保持简短：`global/AGENTS.md` 不超过 70 行，提醒摘要不超过 3 行。新规则先问：能否改由 hook 或 lint 检查？
- 新发现的 Codex 行为写进 `playbook/lessons.md`，沿用"现象、原因、对策"的结构。
- 门禁：`python -X utf8 -m unittest discover -s tests`。
