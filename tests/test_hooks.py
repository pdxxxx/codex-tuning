"""Behavior tests for the Stop and UserPromptSubmit hooks."""

import tempfile
import unittest
import uuid

from helpers import ROOT, Repo, go_func, run_hook

GUARD = ROOT / "global" / "hooks" / "style_guard.py"
REMINDER = ROOT / "global" / "hooks" / "style_reminder.py"


def guard_reason(cwd, **payload):
    output = run_hook(GUARD, cwd, **payload)
    return output["reason"] if output else ""


class StyleGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.repo = Repo(self.tmp.name)
        self.repo.write("pkg/a/a.go", "package a\n\n" + go_func("Small", 3))
        self.repo.write("pkg/a/legacy.go", "package a\n\n" + go_func("Legacy", 100))
        self.repo.write("package.json", "{}\n")
        self.repo.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        self.repo.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reports_each_violation_kind(self):
        r = self.repo
        r.write("pkg/a/a.go", "package a\n\n" + go_func("Big", 90))
        r.write("pkg/a/review_round2_test.go", "package a\n")
        r.write("pkg/b/b.go", "package b\n")
        r.write("docs/notes.md", "The2026-10-28 policy supersedes the old one.\n")
        r.write("docs/deployment-2026-10-29.md", "x\n")
        r.write("local-commit-plan.md", "x\n")
        r.write("run.log", "x\n")
        r.write("pnpm-lock.yaml", "lockfileVersion: '9.0'\nrewritten: true\n")
        r.write("pkg/a/wide.go", "package a\n\nvar x = \"" + "y" * 130 + "\"\n")
        reason = guard_reason(r.root)
        for expected in ("函数 Big 有 92 行", "review_round2_test.go", "pkg/b/: 新建了 Go 包", "supersede",
                         "单词和日期粘连", "deployment-2026-10-29.md", "local-commit-plan.md", "run.log",
                         "pnpm-lock.yaml: 锁文件被改写", "wide.go: 1 行"):
            self.assertIn(expected, reason)

    def test_clean_tree_is_silent(self):
        self.assertEqual(guard_reason(self.repo.root), "")

    def test_skips_when_already_continuing_after_a_block(self):
        self.repo.write("run.log", "x\n")
        self.assertEqual(guard_reason(self.repo.root, stop_hook_active=True), "")

    def test_outside_git_is_silent(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(guard_reason(plain), "")

    def test_reports_a_finding_once_per_session(self):
        self.repo.write("run.log", "x\n")
        session = str(uuid.uuid4())
        self.assertIn("run.log", guard_reason(self.repo.root, session_id=session))
        self.assertEqual(guard_reason(self.repo.root, session_id=session), "")

    def test_allows_small_growth_of_an_already_long_function(self):
        self.repo.write("pkg/a/legacy.go", "package a\n\n" + go_func("Legacy", 103))
        self.assertEqual(guard_reason(self.repo.root), "")

    def test_reports_large_growth_of_an_already_long_function(self):
        self.repo.write("pkg/a/legacy.go", "package a\n\n" + go_func("Legacy", 130))
        self.assertIn("本轮又增加 30 行", guard_reason(self.repo.root))

    def test_reports_a_function_that_crosses_the_limit(self):
        self.repo.write("pkg/a/a.go", "package a\n\n" + go_func("Small", 85))
        self.assertIn("函数 Small 有 87 行", guard_reason(self.repo.root))

    def test_repository_config_can_disable_checks(self):
        self.repo.write(".codex-style.json", '{"enabled": false}\n')
        self.repo.write("run.log", "x\n")
        self.assertEqual(guard_reason(self.repo.root), "")

    def test_repository_config_can_raise_limits(self):
        self.repo.write(".codex-style.json", '{"max_func_lines": 100}\n')
        self.repo.write("pkg/a/a.go", "package a\n\n" + go_func("Small", 85))
        self.assertEqual(guard_reason(self.repo.root), "")

    def test_ignores_tool_managed_directories(self):
        self.repo.write(".agents/skills/x.md", "This supersedes that.\n")
        self.assertEqual(guard_reason(self.repo.root), "")


class StyleReminderTest(unittest.TestCase):
    def test_injects_the_digest(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            output = run_hook(REMINDER, Repo(tmp).root)
        self.assertIn("[engineering-style]", output["hookSpecificOutput"]["additionalContext"])

    def test_stays_silent_when_the_repository_disables_style_checks(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = Repo(tmp)
            repo.write(".codex-style.json", '{"enabled": false}\n')
            repo.write("sub/file.txt", "x\n")
            self.assertIsNone(run_hook(REMINDER, repo.root / "sub"))


if __name__ == "__main__":
    unittest.main()
