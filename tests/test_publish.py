import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PUBLISHER = Path(__file__).resolve().parents[1] / "scripts/open_update_pr.sh"


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.work)], check=True, capture_output=True)
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("checkout", "-b", "main")
        (self.work / "Formula").mkdir()
        (self.work / "Formula/attention.rb").write_text('version "0.1.7"\n')
        (self.work / "README.md").write_text("Original guide\n")
        self.git("add", ".")
        self.git("commit", "-m", "chore: initial fixture")
        self.git("push", "origin", "main")
        self.base = self.git("rev-parse", "HEAD").strip()
        binary = self.root / "bin"
        binary.mkdir()
        # The GitHub API is the only external mutation replaced in this fixture.
        (binary / "gh").write_text('''#!/usr/bin/env python3
import os, pathlib, sys
assert sys.argv[1:3] == ['pr', 'create'], sys.argv
body = pathlib.Path(sys.argv[sys.argv.index('--body-file') + 1]).read_text()
pathlib.Path(os.environ['PR_RECORD']).write_text(body)
print('https://github.com/xiaofei-du/homebrew-tap/pull/123')
''')
        (binary / "gh").chmod(0o755)
        self.env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
                        UPDATE_VERSION="0.1.8", SOURCE_SHA="a" * 40, ARCHIVE_SHA256="b" * 64,
                        UPSTREAM_RUN_URL="https://github.com/xiaofei-du/attention/actions/runs/123",
                        RUNNER_TEMP=str(self.root), GITHUB_OUTPUT=str(self.root / "output"),
                        PR_RECORD=str(self.root / "pr"))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.work, text=True, stderr=subprocess.PIPE)

    def publish(self):
        (self.work / "Formula/attention.rb").write_text('version "0.1.8"\n')
        (self.work / "README.md").write_text("Updated guide\n")
        (self.work / "unrelated.txt").write_text("Never include this file\n")
        self.git("add", "unrelated.txt")
        return subprocess.run(["bash", str(PUBLISHER)], cwd=self.work, env=self.env,
                              capture_output=True, text=True)

    def test_new_branch_and_pr_include_only_the_release_update(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        head = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/automation/attention-0.1.8").split()[0], head)
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines(),
                         ["Formula/attention.rb", "README.md"])
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/main").split()[0], self.base)
        self.assertEqual((self.root / "output").read_text(), f"head_sha={head}\n")
        self.assertIn("**Because**", (self.root / "pr").read_text())

    def test_branch_created_after_planning_is_never_overwritten(self):
        # Even a fast-forward would be forbidden: the empty lease is create-only.
        self.git("push", "origin", "HEAD:refs/heads/automation/attention-0.1.8")
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale info", result.stderr)
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/automation/attention-0.1.8").split()[0], self.base)
        self.assertFalse((self.root / "pr").exists())


if __name__ == "__main__":
    unittest.main()
