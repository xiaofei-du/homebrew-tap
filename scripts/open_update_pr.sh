#!/usr/bin/env bash
set -euo pipefail

# Only called after the planner validates and edits these two files.
[[ "$UPDATE_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$UPSTREAM_RUN_URL" =~ ^https://github.com/xiaofei-du/attention/actions/runs/[0-9]+$ ]]
branch="automation/attention-$UPDATE_VERSION"
title="chore(attention): update formula to $UPDATE_VERSION"
body="$RUNNER_TEMP/attention-update-body.md"
cat > "$body" <<EOF
**Because**

- Attention $UPDATE_VERSION passed [upstream macOS CI]($UPSTREAM_RUN_URL).

**This commit**

- Pin the formula and guide to $SOURCE_SHA.
- Verify the source and both packaged plugin versions; archive SHA-256: $ARCHIVE_SHA256.
- Request Homebrew installation, upgrade, tests, audit, reinstall and removal on Apple Silicon and Intel. Wait for both to pass before merging; this workflow does not auto-merge.
EOF
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -- Formula/attention.rb README.md
{ printf '%s\n\n' "$title"; cat "$body"; } > "$RUNNER_TEMP/attention-update-commit.txt"
git -c core.hooksPath=/dev/null commit --only -F "$RUNNER_TEMP/attention-update-commit.txt" -- Formula/attention.rb README.md
# An empty lease means this ref MUST NOT exist. Git enforces this atomically:
# even a branch created after planning is rejected, never reset or overwritten.
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' \
  push --force-with-lease="refs/heads/$branch:" origin "HEAD:refs/heads/$branch"
gh pr create --repo xiaofei-du/homebrew-tap --base main --head "$branch" \
  --title "$title" --body-file "$body"
printf 'head_sha=%s\n' "$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"
