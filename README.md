# codex-tuning

让 Codex 写出人能维护的代码。这个仓库收集了三类东西：

- **装进 Codex 的部分**：全局规则、每轮提醒 hook、结束时检查 diff 的 hook，以及把它们同步到 `~/.codex` 的安装脚本。
- **给人用的部分**：仓库体检工具、工作流、审阅清单、提示词模板。
- **经验**：用 Codex 开发和整改一个真实项目时观察到的行为模式和对策。

## 目录

```
global/AGENTS.md            全局规则，安装到 ~/.codex/AGENTS.md 的标记块中
global/hooks/style_reminder.py  UserPromptSubmit：每轮注入 3 行规则摘要，上下文压缩后仍然有效
global/hooks/style_guard.py     Stop：检查本轮 diff，发现问题时拦一次，让 Codex 修复或说明
install.py                  安装、更新、卸载；只改自己的部分，并备份改动过的文件
tools/audit_repo.py         仓库体检：规模、超长函数、超长行、命名、概念词频率、文档量、提交粒度
playbook/workflow.md        规则放在哪、一个任务的节奏、什么时候用 /goal
playbook/review-checklist.md 审 Codex 的规划和交付时看什么
playbook/lessons.md         观察到的 Codex 行为和对策
prompts/                    可直接粘贴的提示词模板
tests/                      hook、安装脚本和体检工具的行为测试
```

## 安装

需要 Python 3.10 以上和 git。

```powershell
python install.py --dry-run   # 先看会改什么
python install.py             # 写入 ~/.codex，原文件备份到 ~/.codex/backups/
```

第一次安装或 hook 命令变化后，在 Codex 里运行 `/hooks` 批准。只更新脚本内容、命令不变时不需要重新批准。如果 hook 没有生效，确认你的 Codex 版本已开启 hooks 功能（部分版本需要在 `config.toml` 的 `[features]` 中打开）。

修改规则时只改本仓库，然后重新运行 `install.py`。不要直接编辑 `~/.codex` 里的副本，下次安装会覆盖它。

卸载：`python install.py --uninstall`。它只删除本项目写入的标记块、hook 条目和脚本。

## 仓库级配置

在某个仓库根目录放 `.codex-style.json`，可以调整或关闭检查。例如维护一个不打算整改的旧仓库时：

```json
{"enabled": false}
```

也可以只调整上限：`{"max_func_lines": 100, "max_line_chars": 140, "func_growth_allowance": 20}`。

Stop hook 的长度规则只针对本轮新写或修改的代码。已经超长的旧函数只在一次增长超过 `func_growth_allowance` 行时才报告，所以热修复不会被逼成重构。

## 体检一个仓库

```powershell
python tools/audit_repo.py D:\path\to\repo > audit.md
```

只读，只看被 git 跟踪的文件，跳过 `.agents/`、`.claude/` 这类工具目录。拿到报告后，配合 `prompts/audit-codebase.md` 做一次完整审查。

## 测试

```powershell
python -X utf8 -m unittest discover -s tests
```

测试在临时 git 仓库和临时 Codex 目录里运行，不会碰到真实的 `~/.codex`。
