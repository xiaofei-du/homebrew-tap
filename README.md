# Xiaofei Du's Homebrew tap

## Attention! 📣

Local spoken coding-agent notifications for macOS 14.2+, with one plugin per
Codex/Claude Code client.

```sh
brew install xiaofei-du/tap/attention
attention setup
```

Use `attention update` to update existing enabled client plugins. Disabled plugins
are skipped. Finish active tasks and reload clients after updates.

To remove Attention from both clients, its private data and the Homebrew command:

```sh
attention uninstall
```

The command previews the scope and asks for confirmation. Shared uv/Python and
this tap are retained. All Homebrew versions of Attention are removed. Cancelling
or failed cleanup keeps the command available.
`brew uninstall attention` alone removes only the command, leaving plugins and
settings intact. See the [Attention guide](https://github.com/xiaofei-du/attention/blob/f8711397c227c683418f342bdffb29c2f0d60959/docs/homebrew.md)
for custom profiles, offline cleanup and manual installation.

Homebrew distributes the management command and depends on uv. Native plugin
managers own the plugins; the tap does not install another runtime or trust hooks.
`brew upgrade xiaofei-du/tap/attention` updates the management command itself.

## Maintaining the formula

Pin the source URL to a full Attention Git commit and set its SHA-256 and version.
Confirm that Attention's macOS tests passed for that commit before publishing the bump.
The formula installs only the command and the two setup/cleanup helpers from the
archive. Do not add post-install hooks that modify client profiles.

Validate changes with `brew audit --strict xiaofei-du/tap/attention` and
`brew test xiaofei-du/tap/attention`. The workflow tests Apple Silicon and Intel
installation, reinstall, test execution and removal with disposable homes.
Its upgrade test reads the target version from the formula and uses a synthetic
older version, so new releases do not require editing the workflow's expectations.
Full setup/update/cleanup behavior and native-client protocol fixtures live in
the Attention repository's test suite. No CI test plays audio.

Use Conventional Commit subjects and the **Because** / **This commit** body format.

## Automatic updates

When Attention's `macOS tests` succeeds for a push to `main`, its release workflow
compares the version with this formula. A newer version triggers this tap's
**Sync Attention** workflow. There is no cron job and no periodic polling.
Merging an earlier formula update also checks for any newer version that arrived
while that PR was awaiting review.

The tap independently verifies that upstream main passed CI, checks that the source
and both packaged plugins agree on the version, and calculates the pinned archive's
SHA-256. It opens one update PR and explicitly starts the existing Homebrew tests
on Apple Silicon and Intel. A maintainer reviews and merges after both pass.
It does not modify user installations or automatically merge or downgrade.

An open update PR is left untouched. Repeated events do not start the same tests
again, including failed tests; use **Re-run failed jobs** after investigating a
failure. Closing a version's PR declines that version: reopen it to reconsider.
If a dispatch failed before tests started, rerun **Sync Attention** to recover.
If creating the PR failed after its branch was pushed, inspect that branch and
open its PR manually. Publication only creates a new branch; it never overwrites
an existing one, even if another process creates it after the initial check.

GitHub may show **Approve workflows to run** on a bot-created PR. The updater
separately dispatches the Homebrew checks so they run without that approval.
Approving the PR-triggered workflow is optional and starts another real test run;
the workflow never substitutes skipped checks for passing tests. Maintainer edits
to an update PR receive normal PR CI.

To check immediately, use **Actions → Sync Attention → Run workflow** on `main`.
Select `dry_run` to view changes without creating a PR or starting Mac tests.
Local maintainer check (writes only the formula and pinned guide link):

```sh
python3 -m unittest discover -s tests -v
python3 scripts/sync_attention.py
git diff -- Formula/attention.rb README.md
```

The cross-repository trigger uses an Attention repository secret named
`HOMEBREW_TAP_TOKEN`: a fine-grained token limited to this tap, with **Actions:
read and write** (and GitHub's required read-only Metadata permission). It does
not need Contents or Pull requests write access. Store it directly in GitHub;
never paste it into a chat or commit it. Rotate it before its expiry. A GitHub
App installation token with the same scope can replace it later.

This tap uses its own short-lived `GITHUB_TOKEN` to create PRs and dispatch tests.
Enable **Settings → Actions → General → Allow GitHub Actions to create and approve
pull requests**; the workflow creates PRs but never approves them. The default
repository workflow permission remains read-only, and Mac tests have no write
permission. Public-repository standard runners are free; this workflow uses no
LLM, additional package dependencies, or uploaded artifacts.
