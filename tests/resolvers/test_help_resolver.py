"""Tests for the generic binary-help subcommand resolver.

The harness runs REAL fake binaries (shell scripts on a tmp PATH) that
append their argv to a log file, so every claim about spawning (or not
spawning) `binary --help` is grounded in the argv log, not in the
resolver's return value alone.
"""
import os
import time

import pytest

from thefuck import shell_ast, typo
from thefuck.resolvers.help_resolver import get_help_correction


pytestmark = [
    pytest.mark.skipif(
        not shell_ast.AST_AVAILABLE, reason='bashlex is not available'),
    pytest.mark.skipif(
        os.name == 'nt', reason='fake binaries are POSIX shell scripts'),
]


def _make_fake(path, argv_log, commands, exec_sleep=0):
    """Writes an executable fake binary.

    It appends its argv to `argv_log`, records its pid, optionally
    `exec`s a `sleep` (replacing itself, so a kill leaves no orphan)
    before printing a `Commands:` section built from `commands`.
    """
    body = [
        '#!/bin/sh',
        "printf '%s\\n' \"$*\" >> {}".format(argv_log),
        'echo $$ > {}'.format(path + '.pid'),
    ]
    if exec_sleep:
        body.append('exec sleep {}'.format(exec_sleep))
    if commands is not None:
        body.append("cat <<'EOF'")
        body.append('Usage: {} COMMAND [arg...]'.format(
            os.path.basename(path)))
        body.append('')
        body.append('Commands:')
        for command in commands:
            body.append('  {}'.format(command))
        body.append('')
        body.append("Run '{} COMMAND --help' for more information.".format(
            os.path.basename(path)))
        body.append('EOF')
    with open(path, 'w') as script:
        script.write('\n'.join(body) + '\n')
    os.chmod(path, 0o755)


@pytest.fixture
def fake_bin(tmpdir, os_environ, no_memoize):
    """Puts a tmp bin dir first on PATH; returns a binary factory."""
    bindir = tmpdir.mkdir('bin')
    os_environ['PATH'] = str(bindir) + os.pathsep + os_environ['PATH']

    def _factory(name, commands=('build', 'clean', 'pull'), exec_sleep=0):
        path = str(bindir.join(name))
        _make_fake(path, str(tmpdir.join('argv.log')), commands, exec_sleep)
        return path

    return _factory


@pytest.fixture
def argv_log(tmpdir):
    return str(tmpdir.join('argv.log'))


@pytest.fixture
def enable_cache(no_cache, monkeypatch, tmpdir, os_environ):
    """Re-enables the mtime cache that the autouse no_cache disables."""
    os_environ['XDG_CACHE_HOME'] = str(tmpdir.mkdir('cache'))
    monkeypatch.setattr('thefuck.utils.cache.disabled', False)


def _spawned(argv_log):
    if not os.path.exists(argv_log):
        return []
    with open(argv_log) as log:
        return log.read().splitlines()


def test_returns_correction_when_subcommand_misspelled(
        fake_bin, argv_log, enable_cache):
    fake_bin('fake')
    assert get_help_correction('fake bilud .') == 'fake build .'
    # The mtime-keyed cache suppresses the second `--help` spawn.
    assert get_help_correction('fake bilud .') == 'fake build .'
    assert _spawned(argv_log) == ['--help']


def test_corrects_transposed_subcommand(fake_bin, argv_log, enable_cache):
    # bulid -> build scores 2 * 4 / 10 = 0.8, right at the cutoff,
    # and is also a single transposition (li <-> il).
    fake_bin('fake')
    assert get_help_correction('fake bulid .') == 'fake build .'
    assert typo.single_edit('bulid', 'build')


def test_corrects_transposition_under_cutoff(
        fake_bin, argv_log, enable_cache):
    # psuh -> push scores 2 * 3 / 8 = 0.75, under the cutoff, so only
    # the first-char-equal single-edit match fixes it.
    fake_bin('fake', commands=('push', 'build', 'clean'))
    assert get_help_correction('fake psuh x') == 'fake push x'


def test_respawns_when_binary_mtime_changes(
        fake_bin, argv_log, enable_cache):
    path = fake_bin('fake')
    assert get_help_correction('fake bilud .') == 'fake build .'
    stats = os.stat(path)
    os.utime(path, (stats.st_atime, stats.st_mtime + 5))
    assert get_help_correction('fake bilud .') == 'fake build .'
    assert _spawned(argv_log) == ['--help', '--help']


def test_declines_when_help_times_out(fake_bin, argv_log, enable_cache):
    path = fake_bin('sleeper', commands=None, exec_sleep=5)
    started = time.time()
    assert get_help_correction('sleeper whatever') is None
    elapsed = time.time() - started
    # The spawn really happened and the process was killed, not waited out.
    assert _spawned(argv_log) == ['--help']
    with open(path + '.pid') as pid_file:
        pid = int(pid_file.read())
    with pytest.raises(OSError):
        os.kill(pid, 0)
    assert elapsed < 3


def test_declines_when_token_is_flag(fake_bin, argv_log):
    fake_bin('fake')
    assert get_help_correction('fake --bilud') is None
    assert _spawned(argv_log) == []


def test_declines_when_subcommand_is_listed(
        fake_bin, argv_log, enable_cache):
    fake_bin('fake')
    assert get_help_correction('fake build .') is None
    assert get_help_correction('fake build .') is None
    assert _spawned(argv_log) == ['--help']


def test_declines_when_head_not_on_path(fake_bin, argv_log):
    assert get_help_correction('no-such-binary-anywhere xyz') is None
    assert _spawned(argv_log) == []


def test_declines_when_match_is_ambiguous(fake_bin, argv_log):
    fake_bin('fake', commands=('clean', 'cleat', 'build', 'pull'))
    assert get_help_correction('fake clea') is None


def test_declines_when_head_is_sudo(fake_bin, argv_log):
    fake_bin('fake')
    assert get_help_correction('sudo fake bilud') is None
    assert _spawned(argv_log) == []


def test_declines_when_script_unparseable(fake_bin, argv_log):
    fake_bin('fake')
    # bashlex cannot parse `case`; the flat fallback's head token then
    # fails the resolver's gates and nothing is spawned.
    assert get_help_correction('case $x in a) fake bilud;; esac') is None
    assert _spawned(argv_log) == []
