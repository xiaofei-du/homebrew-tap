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
This CI validates formula changes; upstream release discovery and tap updates are
not automated yet.
Full setup/update/cleanup behavior and native-client protocol fixtures live in
the Attention repository's test suite. No CI test plays audio.

Use Conventional Commit subjects and the **Because** / **This commit** body format.
