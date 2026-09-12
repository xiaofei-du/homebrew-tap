import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts.sync_attention import prepare_update, ensure_tests


SHA = "a" * 40
OLD_SHA = "b" * 40
UPSTREAM = "xiaofei-du/attention"
TAP = "xiaofei-du/homebrew-tap"


def archive(version="0.1.8", plugin_version=None, symlink=False):
    contents = {
        "pyproject.toml": f'[project]\nversion = "{version}"\n',
        "plugins/attention/.codex-plugin/plugin.json": json.dumps(
            {"name": "attention", "version": plugin_version or version}),
        "claude-plugins/attention/.claude-plugin/plugin.json": json.dumps(
            {"name": "attention", "version": version}),
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, value in contents.items():
            info = tarfile.TarInfo(f"attention-{SHA}/{path}")
            data = value.encode()
            info.size = len(data)
            if symlink and path == "pyproject.toml":
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                info.size = 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "Formula").mkdir()
        self.formula = self.root / "Formula/attention.rb"
        self.formula.write_text(
            'class Attention < Formula\n'
            f'  url "https://github.com/{UPSTREAM}/archive/{OLD_SHA}.tar.gz"\n'
            '  version "0.1.7"\n'
            f'  sha256 "{"c" * 64}"\n'
            '  def install\n    bin.install "attention"\n  end\nend\n')
        self.readme = self.root / "README.md"
        self.readme.write_text(
            f"Guide: https://github.com/{UPSTREAM}/blob/{OLD_SHA}/docs/homebrew.md\n"
            "User-facing installation instructions stay unchanged.\n")
        self.original = (self.formula.read_text(), self.readme.read_text())
        self.version = "0.1.8"
        self.bundle = archive()
        self.downloads = []
        self.open_prs = []
        self.previous_prs = []
        self.run = {
            "id": 123, "head_sha": SHA, "head_branch": "main", "event": "push",
            "path": ".github/workflows/tests.yml", "status": "completed",
            "conclusion": "success", "head_repository": {"full_name": UPSTREAM},
        }

    def api(self, path):
        if path == f"repos/{UPSTREAM}/commits/main":
            return {"sha": SHA}
        if path == f"repos/{UPSTREAM}/contents/pyproject.toml?ref={SHA}":
            return {"encoding": "base64", "content": base64.b64encode(
                f'[project]\nversion = "{self.version}"\n'.encode()).decode()}
        if path == f"repos/{UPSTREAM}/actions/workflows/tests.yml/runs?branch=main&event=push&head_sha={SHA}&per_page=1":
            return {"workflow_runs": [self.run] if self.run else []}
        if path == f"repos/{TAP}/pulls?state=open&base=main&per_page=100":
            return self.open_prs
        if path == f"repos/{TAP}/pulls?state=all&head=xiaofei-du%3Aautomation%2Fattention-{self.version}&base=main&per_page=100":
            return self.previous_prs
        raise AssertionError(f"Unexpected API call: {path}")

    def download(self, url):
        self.assertEqual(url, f"https://github.com/{UPSTREAM}/archive/{SHA}.tar.gz")
        self.downloads.append(url)
        return self.bundle

    def prepare(self):
        return prepare_update(self.root, self.api, self.download)

    def assert_unchanged(self):
        self.assertEqual((self.formula.read_text(), self.readme.read_text()), self.original)

    def test_tested_new_version_updates_only_release_fields(self):
        result = self.prepare()
        self.assertTrue(result["changed"])
        expected = self.original[0].replace(OLD_SHA, SHA).replace('"0.1.7"', '"0.1.8"')
        expected = expected.replace("c" * 64, hashlib.sha256(self.bundle).hexdigest())
        self.assertEqual(self.formula.read_text(), expected)
        self.assertEqual(self.readme.read_text(), self.original[1].replace(OLD_SHA, SHA))
        self.assertEqual(result["branch"], "automation/attention-0.1.8")
        self.assertEqual(result["run_url"], f"https://github.com/{UPSTREAM}/actions/runs/123")

    def test_same_or_older_version_does_not_download_or_rewrite(self):
        for version in ("0.1.7", "0.1.6"):
            with self.subTest(version=version):
                self.version = version
                self.assertFalse(self.prepare()["changed"])
                self.assertEqual(self.downloads, [])
                self.assert_unchanged()

    def test_numeric_versions_handle_two_digit_minor(self):
        self.version = "0.10.0"
        self.bundle = archive(self.version)
        self.assertTrue(self.prepare()["changed"])

    def test_untrusted_or_prerelease_version_fails_before_writing(self):
        for value in ("0.1.8-rc1", "v0.1.8", "01.2.3", "$(touch /tmp/pwned)", "1.2.3\\nnew-output=true"):
            with self.subTest(value=value):
                self.version = value
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assert_unchanged()
        self.assertEqual(self.downloads, [])

    def test_unfinished_failed_missing_or_wrong_commit_ci_never_releases(self):
        original = self.run.copy()
        cases = [None, {"status": "in_progress"}, {"conclusion": "failure"},
                 {"head_sha": OLD_SHA}, {"head_branch": "feature"},
                 {"event": "pull_request"}, {"path": ".github/workflows/other.yml"},
                 {"head_repository": {"full_name": "other/attention"}}]
        for change in cases:
            with self.subTest(change=change):
                self.run = None if change is None else original | change
                self.assertFalse(self.prepare()["changed"])
                self.assert_unchanged()
        self.assertEqual(self.downloads, [])

    def test_inconsistent_archive_or_plugin_version_rejected(self):
        for bundle in (archive("0.1.9"), archive(plugin_version="0.1.7"), archive(symlink=True)):
            with self.subTest():
                self.bundle = bundle
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assert_unchanged()

    def test_bad_formula_or_missing_guide_pin_never_partially_writes(self):
        self.readme.write_text("Guide link was moved by a maintainer.\n")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.formula.read_text(), self.original[0])
        self.readme.write_text(self.original[1])
        self.formula.write_text(self.original[0] + '  version "9.9.9"\n')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.readme.read_text(), self.original[1])

    def test_pending_bot_pr_is_not_overwritten_and_retains_test_target(self):
        self.open_prs = [{"number": 7, "user": {"login": "github-actions[bot]"},
                         "head": {"ref": "automation/attention-0.1.8", "sha": SHA,
                                  "repo": {"full_name": TAP}}}]
        result = self.prepare()
        self.assertFalse(result["changed"])
        self.assertEqual(result["branch"], "automation/attention-0.1.8")
        self.assertEqual(result["head_sha"], SHA)
        self.assert_unchanged()

    def test_human_owned_automation_branch_is_not_dispatched(self):
        self.open_prs = [{"number": 7, "user": {"login": "xiaofei-du"},
                         "head": {"ref": "automation/attention-0.1.8", "sha": SHA,
                                  "repo": {"full_name": TAP}}}]
        result = self.prepare()
        self.assertFalse(result["changed"])
        self.assertNotIn("head_sha", result)
        self.assert_unchanged()

    def test_closed_update_is_not_reopened_on_the_next_event(self):
        self.previous_prs = [{"number": 7, "state": "closed"}]
        self.assertFalse(self.prepare()["changed"])
        self.assertEqual(self.downloads, [])
        self.assert_unchanged()


class DispatchTests(unittest.TestCase):
    def call(self, *, runs=None, remote_sha=SHA, branch="automation/attention-0.1.8"):
        self.events = []

        def api(path, data=None):
            self.events.append((path, data))
            if path == f"repos/{TAP}/commits/{branch}":
                return {"sha": remote_sha}
            if path == f"repos/{TAP}/actions/workflows/tests.yml/runs?head_sha={SHA}&per_page=100":
                return {"workflow_runs": runs or []}
            if path == f"repos/{TAP}/actions/workflows/tests.yml/dispatches":
                return None
            raise AssertionError(path)

        return ensure_tests(branch, SHA, api)

    def test_new_bot_head_dispatches_tests_with_the_exact_commit(self):
        self.assertEqual(self.call(), "dispatched")
        self.assertEqual(self.events[-1], (
            f"repos/{TAP}/actions/workflows/tests.yml/dispatches",
            {"ref": "automation/attention-0.1.8", "inputs": {"expected_sha": SHA}}))

    def test_existing_run_is_not_repeated_even_after_failure(self):
        for status in ("queued", "in_progress", "completed"):
            self.assertEqual(self.call(runs=[{"status": status, "conclusion": "failure",
                                             "event": "workflow_dispatch",
                                             "display_title": f"Homebrew ({SHA})"}]), "already requested")
            self.assertTrue(all(data is None for _, data in self.events))

    def test_dispatch_that_raced_to_another_commit_does_not_suppress_correct_test(self):
        self.assertEqual(self.call(runs=[{"event": "workflow_dispatch", "status": "completed",
                                         "conclusion": "failure", "display_title": f"Homebrew ({OLD_SHA})"}]), "dispatched")

    def test_human_push_pr_ci_counts_but_skipped_bot_pr_ci_does_not(self):
        run = {"event": "pull_request", "display_title": f"Homebrew ({SHA})"}
        self.assertEqual(self.call(runs=[run | {"actor": {"login": "xiaofei-du"}}]), "already requested")
        self.assertEqual(self.call(runs=[run | {"actor": {"login": "github-actions[bot]"}}]), "dispatched")

    def test_changed_branch_or_unexpected_target_cannot_start_tests(self):
        for options in ({"remote_sha": OLD_SHA}, {"branch": "main"}, {"branch": "other/feature"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.call(**options)
            self.assertTrue(all(data is None for _, data in self.events))


if __name__ == "__main__":
    unittest.main()
