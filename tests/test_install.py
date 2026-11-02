"""Behavior tests for install.py against a throwaway Codex home directory."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run_python

INSTALL = ROOT / "install.py"
OTHER_AGENTS = (
    "# Other rules\n\n<!-- engineering-style:start old -->\nold rules\n<!-- engineering-style:end -->\n\n# Tail\n"
)
OTHER_HOOKS = {"hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python other_start.py"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python other_stop.py"}]}],
}}


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        (self.home / "AGENTS.md").write_text(OTHER_AGENTS, encoding="utf-8")
        (self.home / "hooks.json").write_text(json.dumps(OTHER_HOOKS), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        return run_python(INSTALL, "--codex-home", str(self.home), *args)

    def snapshot(self):
        files = [p for p in self.home.rglob("*") if p.is_file() and "backups" not in p.parts]
        return {p.relative_to(self.home).as_posix(): p.read_text(encoding="utf-8") for p in files}

    def stop_commands(self):
        hooks = json.loads((self.home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        return [hook["command"] for group in hooks.get("Stop", []) for hook in group["hooks"]]

    def test_replaces_its_block_and_keeps_other_content(self):
        self.install()
        agents = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count("<!-- engineering-style:start"), 1)
        self.assertNotIn("old rules", agents)
        self.assertIn("# Other rules", agents)
        self.assertIn("# Tail", agents)
        self.assertIn("## 修改已有代码", agents)

    def test_adds_its_hooks_and_keeps_other_hooks(self):
        self.install()
        hooks = json.loads((self.home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(hooks["SessionStart"], OTHER_HOOKS["hooks"]["SessionStart"])
        commands = self.stop_commands()
        self.assertEqual(commands[0], "python other_stop.py")
        self.assertEqual(sum("style_guard.py" in c for c in commands), 1)
        self.assertTrue((self.home / "hooks" / "style_guard.py").is_file())
        self.assertTrue((self.home / "hooks" / "style_reminder.py").is_file())

    def test_second_install_changes_nothing(self):
        self.install()
        first = self.snapshot()
        self.assertIn("已是最新", self.install())
        self.assertEqual(self.snapshot(), first)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        output = self.install("--dry-run")
        self.assertEqual(self.snapshot(), before)
        self.assertIn("AGENTS.md", output)

    def test_backs_up_changed_files(self):
        self.install()
        backups = list((self.home / "backups").rglob("AGENTS.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), OTHER_AGENTS)

    def test_uninstall_removes_only_what_it_installed(self):
        self.install()
        self.install("--uninstall")
        agents = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("engineering-style", agents)
        self.assertIn("# Other rules", agents)
        self.assertIn("# Tail", agents)
        self.assertEqual(self.stop_commands(), ["python other_stop.py"])
        self.assertFalse((self.home / "hooks" / "style_guard.py").exists())


if __name__ == "__main__":
    unittest.main()
