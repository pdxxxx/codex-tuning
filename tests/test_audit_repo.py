"""Smoke test for the repository audit report."""

import tempfile
import unittest

from helpers import ROOT, Repo, go_func, run_python

AUDIT = ROOT / "tools" / "audit_repo.py"


class AuditRepoTest(unittest.TestCase):
    def test_report_shows_each_kind_of_problem(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = Repo(tmp)
            repo.write("internal/a/a.go", "package a\n\n// The fence keeps the lineage exact.\n" + go_func("Big", 90))
            repo.write("internal/a/review_round2_test.go", "package a\n")
            repo.write("docs/deployment-2026-10-29.md", "Release notes.\n")
            repo.write(".agents/skills/progress-notes.md", "Tool-managed skill text.\n")
            repo.commit()
            report = run_python(AUDIT, str(repo.root))
        for expected in ("## 规模", "`internal/a`", "| 92 | `internal/a/a.go` | `Big` |", "review_round2_test.go",
                         "deployment-2026-10-29.md", "| fence | 1 |", "## 提交粒度"):
            self.assertIn(expected, report)
        self.assertNotIn(".agents", report)


if __name__ == "__main__":
    unittest.main()
