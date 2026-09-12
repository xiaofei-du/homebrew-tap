class Attention < Formula
  desc "Manage spoken coding-agent notifications for Codex and Claude Code"
  homepage "https://github.com/xiaofei-du/attention"
  url "https://github.com/xiaofei-du/attention/archive/f8711397c227c683418f342bdffb29c2f0d60959.tar.gz"
  version "0.1.7"
  sha256 "54661bf30653319c3e00db4d374041adf21fc24ff58b36479dbd06d29dd309f4"
  license "MIT"

  depends_on macos: :sonoma
  depends_on "uv"

  def install
    odie "Attention requires macOS 14.2 or later" if MacOS.version < MacOSVersion.new("14.2")

    libexec.install "homebrew/attention", "setup.sh", "uninstall.sh"
    (libexec/"scripts").install "scripts/setup.py", "scripts/uninstall.py"
    (libexec/"VERSION").write "#{version}\n"
    (libexec/"brew-path").write "#{HOMEBREW_PREFIX}/bin/brew\n"
    (libexec/"uv-bin").write "#{formula_opt_bin("uv")}\n"
    bin.install_symlink libexec/"attention"
  end

  def caveats
    <<~EOS
      Install your native client plugins:
        attention setup
      Then reopen Codex/Claude Code and review Attention's hooks.

      Update existing enabled plugins:
        attention update

      Complete removal (quit coding clients first; previews and confirms):
        attention uninstall
      brew uninstall alone removes only this command, not client plugins/data.
    EOS
  end

  test do
    # No client executables on PATH: test real preflight without installing plugins.
    ENV["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    assert_match "codex is not on PATH", shell_output("#{bin}/attention setup --client codex --dry-run 2>&1", 1)
    assert_match version.to_s, shell_output("#{bin}/attention --version")
    assert_match "attention update", shell_output("#{bin}/attention --help")
    assert_path_exists libexec/"scripts/setup.py"
    assert_path_exists libexec/"scripts/uninstall.py"
    refute_path_exists testpath/".codex"
    refute_path_exists testpath/".claude"
    refute_path_exists testpath/"Library/Application Support/Attention"
  end
end
