# 安装 codex-tuning（写给 AI agent）

你正在帮用户把 codex-tuning 的规则和 hook 安装到本机的 Codex（`~/.codex`）。按下面的步骤执行，每一步的输出都简要告诉用户。

## 1. 检查环境

- 需要 git 和 Python 3.10 以上。依次试 `python --version`、`python3 --version`，Windows 上再试 `py -3 --version`，记下第一个满足版本要求的命令，下文称为 `<PY>`。
- 都不满足时停下，告诉用户需要先安装 Python 3.10 以上，不要替用户安装。

## 2. 获取仓库

- 仓库放在 `~/codex-tuning`。以后更新规则时还要用它，所以不要放进临时目录。
- 目录不存在时：`git clone https://github.com/pdxxxx/codex-tuning.git ~/codex-tuning`。
- 目录已存在时：进入目录运行 `git pull --ff-only`。如果失败，停下，把错误告诉用户，不要强制覆盖。

## 3. 预览改动

在 `~/codex-tuning` 下运行：

```
<PY> -X utf8 install.py --dry-run
```

- 安装脚本默认让 hook 用 `python`（Windows）或 `python3`（其他系统）运行。如果 `<PY>` 与默认值不同（例如 Windows 上只有 `py -3`），之后每条 install.py 命令都加上 `--python "<PY> -X utf8"`。
- 用户设置了 `CODEX_HOME` 时，安装脚本会自动使用它。

把预览结果概括给用户：会更新哪些文件，`~/.codex/AGENTS.md` 里新增或改动了哪些规则。然后请用户确认。如果用户在这次请求里已经明确说了"直接安装"，可以跳过确认。

## 4. 安装

```
<PY> -X utf8 install.py
```

安装脚本只改它自己管理的部分：`AGENTS.md` 里的标记块、`hooks.json` 里自己的条目，以及 `hooks/` 下的两个脚本。改动过的原文件会备份到 `~/.codex/backups/`。重复运行是安全的。

## 5. 告诉用户收尾步骤

- 第一次安装，或输出提示 hook 命令有变化时：需要在 Codex 里运行 `/hooks`，批准 `style_reminder.py` 和 `style_guard.py` 两个 hook。
- 如果 hook 没有生效，可能需要在 `~/.codex/config.toml` 的 `[features]` 中打开 hooks 功能。具体键名以用户的 Codex 版本文档为准，不要猜测着写入。
- 备份目录的位置（见安装输出）。
- 卸载方法：`<PY> -X utf8 install.py --uninstall`。
- 以后更新：在 `~/codex-tuning` 里 `git pull`，再运行一次安装。
