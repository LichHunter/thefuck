"""Tests for the error-suggestion resolver.

The main fixture is the byte-exact stderr of `git psuh` captured from
a real git (od -c verified, see .omo/evidence/
task-1-intelligent-correction.txt); one test additionally runs a live
git so the resolver is pinned against the binary, not the fixture.
"""
import os
import shutil
import subprocess

import pytest

from thefuck import shell_ast
from thefuck.resolvers.error_suggestion import get_suggestion_candidates
from thefuck.types import Command

# Real `git psuh` stderr on this machine (87 bytes, stdout empty):
# "git: 'psuh' is not a git command. See 'git --help'.\n"
# "\n"
# "The most similar command is\n"
# "\tpush\n"
_GIT_PSUH_OUTPUT = (
    "git: 'psuh' is not a git command. See 'git --help'.\n"
    "\n"
    "The most similar command is\n"
    "\tpush\n")

# lein-rpl-style output with two suggestions that each pass the
# length-scaled floor for 'rpl' (repl and rple are single edits).
_LEIN_MULTI_OUTPUT = (
    "'rpl' is not a task. See 'lein help'.\n"
    "\n"
    "Did you mean this?\n"
    "         repl\n"
    "         rple\n")

requires_ast = pytest.mark.skipif(not shell_ast.AST_AVAILABLE,
                                  reason='bashlex is not available')


def test_corrects_subcommand_from_git_output():
    command = Command('git psuh', _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) == 'git push'


def test_corrects_token_in_head_position():
    # The binary's error nominates the position: a token in the head
    # is replaced exactly like a subcommand.
    command = Command('psuh origin master', _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) == 'push origin master'


def test_replaces_whole_quoted_span():
    command = Command("git 'psuh'", _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) == 'git push'


def test_replaces_first_occurrence_only():
    command = Command('git psuh psuh', _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) == 'git push psuh'


def test_extracts_capitalized_unknown_command():
    output = "Unknown command 'gti'\n\nDid you mean\n\tgit\n"
    command = Command('gti push', output)
    assert get_suggestion_candidates(command) == 'git push'


def test_extracts_lowercase_unknown_command():
    output = "unknown command 'gti'\n\nDid you mean\n\tgit\n"
    command = Command('gti push', output)
    assert get_suggestion_candidates(command) == 'git push'


def test_duplicate_suggestions_are_not_ambiguity():
    # Two suggestion sections naming the same command collapse into
    # one candidate (unique-survivor semantics); the second section's
    # header is consumed as a separator, the quoted lines unquoted.
    output = ("Unknown command 'psuh'\n"
              "\n"
              "Did you mean\n"
              "    'push'\n"
              "\n"
              "The most similar command\n"
              "    push\n")
    command = Command('git psuh', output)
    assert get_suggestion_candidates(command) == 'git push'


def test_declines_multi_suggestion_output():
    command = Command('lein rpl', _LEIN_MULTI_OUTPUT)
    assert get_suggestion_candidates(command) is None


def test_declines_when_no_suggestion_section():
    output = "git: 'psuh' is not a git command. See 'git --help'.\n"
    command = Command('git psuh', output)
    assert get_suggestion_candidates(command) is None


def test_declines_separator_with_no_lines_after():
    output = ("'psuh' is not a git command.\n"
              "\n"
              "The most similar command is\n")
    command = Command('git psuh', output)
    assert get_suggestion_candidates(command) is None


def test_declines_unrelated_output():
    output = ("E: Could not open lock file /var/lib/dpkg/lock - "
              "open (13: Permission denied)\n")
    command = Command('apt-get install vim', output)
    assert get_suggestion_candidates(command) is None


def test_declines_empty_output():
    command = Command('git psuh', '')
    assert get_suggestion_candidates(command) is None


@requires_ast
def test_declines_when_token_not_in_script():
    command = Command('git checkout', _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) is None


def test_declines_self_suggestion():
    # The binary naming the typed token back is not a fix: a
    # candidate equal to the input would splice to a no-op.
    output = ("'push' is not a task. See 'git help'.\n"
              "\n"
              "Did you mean this?\n"
              "\tpush\n")
    command = Command('git push', output)
    assert get_suggestion_candidates(command) is None


def test_declines_when_suggestion_below_floor():
    # burnnoabcd vs burnno1234 scores 2 * 6 / 20 = 0.6, under the
    # len-10 floor 0.7, and is not a single edit (pinned in
    # tests/resolvers/test_help_resolver.py arithmetic).
    output = ("'burnnoabcd' is not a task.\n"
              "\n"
              "Did you mean this?\n"
              "\tburnno1234\n")
    command = Command('fake burnnoabcd', output)
    assert get_suggestion_candidates(command) is None


def test_returns_none_when_ast_unavailable(monkeypatch):
    monkeypatch.setattr(shell_ast, 'AST_AVAILABLE', False)
    command = Command('git psuh', _GIT_PSUH_OUTPUT)
    assert get_suggestion_candidates(command) is None


def test_corrects_live_git_output(tmpdir):
    if shutil.which('git') is None:
        pytest.skip('git is not available')
    env = dict(os.environ, LC_ALL='C', LANG='C')
    try:
        proc = subprocess.Popen(
            ['git', 'psuh'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=str(tmpdir))
        _, stderr = proc.communicate(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip('git psuh probe failed')
    output = stderr.decode('utf-8', 'replace')
    if ('The most similar command' not in output
            and 'Did you mean' not in output):
        pytest.skip('git prints no suggestions on this machine')
    command = Command('git psuh', output)
    assert get_suggestion_candidates(command) == 'git push'
