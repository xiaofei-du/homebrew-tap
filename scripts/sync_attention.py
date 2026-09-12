"""Prepare a reviewed Homebrew bump from an exact, CI-tested Attention commit.

Uses Python's standard library and gh. Downloaded upstream files are parsed as
data, never executed or extracted. Publication is handled by the workflow.
"""

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
from urllib.parse import urlencode
from urllib.request import urlopen


UPSTREAM = "xiaofei-du/attention"
TAP = "xiaofei-du/homebrew-tap"
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
BRANCH = rf"automation/attention-{VERSION}"


def gh_api(path, data=None):
    args = ["gh", "api", "--method", "GET" if data is None else "POST", path]
    if data is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=None if data is None else json.dumps(data),
                            capture_output=True, text=True, check=True, timeout=60)
    return json.loads(result.stdout) if result.stdout.strip() else None


def download_archive(url):
    # This URL is built from the fixed repository and a validated full commit SHA.
    with urlopen(url, timeout=60) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("Upstream archive exceeds the 64 MiB download limit")
    return data


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(VERSION, value):
        raise ValueError("Expected a stable three-part numeric version")
    return tuple(map(int, value.split(".")))


def single_match(pattern, text):
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching formula field or guide link")
    return matches[0]


def check_archive(data, sha, version):
    paths = ["pyproject.toml", "plugins/attention/.codex-plugin/plugin.json",
             "claude-plugins/attention/.claude-plugin/plugin.json"]
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        for path in paths:
            matches = [m for m in members if m.name == f"attention-{sha}/{path}"]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 1024 * 1024:
                raise ValueError("Archive metadata is missing, duplicated, linked or oversized")
            with tar.extractfile(matches[0]) as source:
                text = source.read().decode("utf-8")
            if path.endswith(".toml"):
                found = tomllib.loads(text)["project"]["version"]
            else:
                manifest = json.loads(text)
                if manifest.get("name") != "attention":
                    raise ValueError("Unexpected packaged plugin name")
                found = manifest["version"]
            if found != version:
                raise ValueError("Source and packaged plugin versions do not agree")


def prepare_update(root, api=gh_api, download=download_archive):
    def skip(reason, **extra):
        return {"changed": False, "reason": reason, **extra}

    prs = api(f"repos/{TAP}/pulls?state=open&base=main&per_page=100")
    # Leave a pending update untouched, including any maintainer edits.
    for pr in prs:
        head = pr["head"]
        if re.fullmatch(BRANCH, head["ref"]) and (head.get("repo") or {}).get("full_name") == TAP:
            extra = {}
            if pr["user"]["login"] == "github-actions[bot]":
                extra = {"branch": head["ref"], "head_sha": head["sha"]}
            return skip(f"Update PR #{pr['number']} is awaiting review", **extra)
    if len(prs) == 100:
        raise ValueError("Open PR list is truncated; refusing to risk a duplicate update")

    formula_path = root / "Formula/attention.rb"
    formula = formula_path.read_text()
    current = single_match(r'^  version "([^"]+)"$', formula).group(1)
    sha = api(f"repos/{UPSTREAM}/commits/main")["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full upstream commit SHA")
    metadata = api(f"repos/{UPSTREAM}/contents/pyproject.toml?ref={sha}")
    if metadata["encoding"] != "base64":
        raise ValueError("Unexpected GitHub content encoding")
    project = tomllib.loads(base64.b64decode(metadata["content"]).decode("utf-8"))
    version = project["project"]["version"]
    if version_tuple(version) <= version_tuple(current):
        return skip(f"Formula {current} is already at or ahead of upstream {version}")

    runs = api(f"repos/{UPSTREAM}/actions/workflows/tests.yml/runs?branch=main&event=push&head_sha={sha}&per_page=1")["workflow_runs"]
    required = {"head_sha": sha, "head_branch": "main", "event": "push",
                "path": ".github/workflows/tests.yml", "status": "completed", "conclusion": "success"}
    if (not runs or any(runs[0].get(k) != v for k, v in required.items())
            or (runs[0].get("head_repository") or {}).get("full_name") != UPSTREAM):
        return skip("The latest macOS tests run for upstream main has not succeeded")
    run_id = runs[0]["id"]
    if not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("Invalid upstream CI run identifier")

    branch = f"automation/attention-{version}"
    query = urlencode({"state": "all", "head": f"xiaofei-du:{branch}", "base": "main", "per_page": 100})
    if api(f"repos/{TAP}/pulls?{query}"):
        return skip(f"An update PR for {version} already exists or was closed; leaving it alone")

    url = f"https://github.com/{UPSTREAM}/archive/{sha}.tar.gz"
    data = download(url)
    check_archive(data, sha, version)
    checksum = hashlib.sha256(data).hexdigest()
    replacements = {
        r'^  url "https://github\.com/xiaofei-du/attention/archive/[0-9a-f]{40}\.tar\.gz"$': f'  url "{url}"',
        r'^  version "[^"]+"$': f'  version "{version}"',
        r'^  sha256 "[0-9a-f]{64}"$': f'  sha256 "{checksum}"',
    }
    for pattern, replacement in replacements.items():
        single_match(pattern, formula)
        formula = re.sub(pattern, lambda _: replacement, formula, flags=re.MULTILINE)
    readme_path = root / "README.md"
    readme = readme_path.read_text()
    guide = r"https://github\.com/xiaofei-du/attention/blob/[0-9a-f]{40}/docs/homebrew\.md"
    single_match(guide, readme)
    readme = re.sub(guide, f"https://github.com/{UPSTREAM}/blob/{sha}/docs/homebrew.md", readme)
    # All metadata and both replacements are validated before either file changes.
    formula_path.write_text(formula)
    readme_path.write_text(readme)
    return {"changed": True, "version": version, "branch": branch, "source_sha": sha,
            "sha256": checksum, "run_url": f"https://github.com/{UPSTREAM}/actions/runs/{run_id}"}


def ensure_tests(branch, head_sha, api=gh_api):
    if not re.fullmatch(BRANCH, branch) or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("Tests can only target a versioned automation branch and full SHA")
    if api(f"repos/{TAP}/commits/{branch}")["sha"] != head_sha:
        raise ValueError("The update branch changed; refusing to test an unexpected commit")
    runs = api(f"repos/{TAP}/actions/workflows/tests.yml/runs?head_sha={head_sha}&per_page=100")
    for run in runs["workflow_runs"]:
        # A branch can move between dispatch and execution. A rejected run for
        # requested A / actual B must not suppress the later valid request for B.
        if run.get("display_title") != f"Homebrew ({head_sha})":
            continue
        if (run.get("event") == "workflow_dispatch" or
                (run.get("event") == "pull_request"
                 and run.get("actor", {}).get("login") != "github-actions[bot]")):
            return "already requested"
    api(f"repos/{TAP}/actions/workflows/tests.yml/dispatches",
        {"ref": branch, "inputs": {"expected_sha": head_sha}})
    return "dispatched"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dispatch-tests", nargs=2, metavar=("BRANCH", "SHA"))
    args = parser.parse_args()
    if args.dispatch_tests:
        print(ensure_tests(*args.dispatch_tests))
        return
    result = prepare_update(args.root)
    print(json.dumps(result, indent=2))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            for key, value in result.items():
                text = str(value).lower() if isinstance(value, bool) else str(value)
                if "\n" in text or "\r" in text:
                    raise ValueError("Multiline workflow output is not allowed")
                stream.write(f"{key}={text}\n")


if __name__ == "__main__":
    main()
