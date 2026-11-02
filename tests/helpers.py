"""Shared helpers for tests that need a throwaway git repository."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def go_func(name, body_lines):
    """Return Go source for a function spanning body_lines + 2 lines."""
    body = "".join(f"\t_ = {i}\n" for i in range(body_lines))
    return f"func {name}() {{\n{body}}}\n"


class Repo:
    def __init__(self, root):
        self.root = Path(root)
        empty_excludes = self.root / ".no-global-excludes"
        self.root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        # Keep the user's global ignore rules from hiding the files under test.
        self.git("config", "core.excludesFile", empty_excludes.as_posix())

    def git(self, *args):
        subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
                       cwd=self.root, check=True, capture_output=True)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message="base"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)


def run_python(script, *args, stdin=""):
    result = subprocess.run([sys.executable, "-X", "utf8", str(script), *args], input=stdin,
                            capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout


def run_hook(script, cwd, **payload):
    """Run a hook script with a JSON payload and return its parsed output, or None when silent."""
    payload.setdefault("cwd", str(cwd))
    output = run_python(script, stdin=json.dumps(payload))
    return json.loads(output) if output.strip() else None
