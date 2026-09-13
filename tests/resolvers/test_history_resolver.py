import difflib

import pytest

from thefuck import shell_ast, typo
from thefuck.resolvers.history_resolver import (
    _CANDIDATES,
    _TOKEN_CUTOFF,
    _prefilter,
    get_history_correction,
)
from thefuck.types import Command

pytestmark = pytest.mark.usefixtures('no_memoize')

requires_ast = pytest.mark.skipif(not shell_ast.AST_AVAILABLE,
                                  reason='bashlex is not available')


@pytest.fixture
def history(mocker):
    def _history(lines):
        return mocker.patch(
            'thefuck.resolvers.history_resolver.'
            'get_valid_history_without_current',
            return_value=lines)
    return _history


def test_corrects_single_diverged_token(history):
    history(['docker build -t foo .'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) == 'docker build -t foo .'


@requires_ast
def test_corrects_two_diverged_tokens_across_segments(history):
    history(['git status | grep -i foo'])
    command = Command('git statuz | greep -i foo', '')
    # statuz -> status scores 2 * 6 / 12 = 0.833 and
    # greep -> grep scores 2 * 4 / 9 = 0.889, both above cutoff.
    assert get_history_correction(command) == 'git status | grep -i foo'


@requires_ast
def test_corrects_transposed_tokens_under_ratio_cutoff(history):
    # psuh -> push and greo -> grep both score 2 * 3 / 8 = 0.75,
    # under _TOKEN_CUTOFF, but each is a first-char-equal single
    # transposition, which the token gate accepts alongside the
    # ratio.
    history(['git push | grep -i foo'])
    command = Command('git psuh | greo -i foo', '')
    assert get_history_correction(command) == 'git push | grep -i foo'


def test_declines_token_just_below_cutoff(history):
    # '--ignore-whitespaces' vs '--ignore-all-spaces' scores
    # 2 * 15 / 39 = 0.769 (under _TOKEN_CUTOFF) AND spans two edits
    # (pinned below), so even the amended single-edit gate declines.
    history(['git diff --ignore-all-spaces HEAD'])
    command = Command('git diff --ignore-whitespaces HEAD', '')
    assert get_history_correction(command) is None
    assert not typo.single_edit('--ignore-whitespaces',
                                '--ignore-all-spaces')


def test_token_cutoff_boundary_arithmetic():
    # 20 + 19 chars with 15 matched: 2 * 15 / 39 = 0.769..., i.e.
    # above the 0.75 the declined flagship typos score but strictly
    # under _TOKEN_CUTOFF, so the boundary is provably tight.
    ratio = difflib.SequenceMatcher(
        None, '--ignore-whitespaces', '--ignore-all-spaces').ratio()
    assert 0.75 <= ratio < _TOKEN_CUTOFF


def test_declines_three_diverged_tokens(history):
    # Every pair alone passes the token cutoff (0.833, 0.909 and
    # 0.8), so only the max-diverged gate rejects this candidate.
    history(['docker status branch build'])
    command = Command('docker statuz brnch bilud', '')
    assert get_history_correction(command) is None


def test_declines_identical_history_line(history):
    # get_valid_history_without_current already drops lines equal to
    # the script; this pins the resolver-side no-op guard for callers
    # that bypass that filter.
    history(['docker bilud -t foo .'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) is None


def test_declines_two_equally_close_candidates(history):
    # bilud -> build (0.8) and bilud -> bild (0.889) both pass every
    # gate, so the resolver declines and the existing history rule
    # keeps offering the choice instead of auto-running one.
    history(['docker build -t foo .', 'docker bild -t foo .'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) is None


def test_repeated_history_line_is_one_candidate(history):
    history(['docker build -t foo .'] * 3)
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) == 'docker build -t foo .'


def test_skips_unparseable_history_line(history):
    # '"foo bar .' never closes its quote, so bashlex refuses the
    # line and shell_ast falls back to a flat view whose token count
    # no longer matches; it is skipped without raising and the valid
    # line still corrects the script.
    history(['docker build -t "foo bar .', 'docker build -t foo .'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) == 'docker build -t foo .'


def test_declines_when_history_is_only_unparseable(history):
    history(['docker build -t "foo bar .'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) is None


def test_flat_mode_corrects_single_edit_tokens(history, monkeypatch):
    # With the parser unavailable both scripts take the flat view;
    # token counts still line up and both diverged tokens are
    # first-char-equal single edits, so the amended gate corrects
    # them there too.
    monkeypatch.setattr(shell_ast, 'AST_AVAILABLE', False)
    history(['git push | grep -i foo'])
    command = Command('git psuh | greo -i foo', '')
    assert get_history_correction(command) == 'git push | grep -i foo'


def test_declines_history_below_prefilter_cutoff(history):
    history(['totally unrelated command here'])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) is None


def test_returns_none_with_empty_history(history):
    history([])
    command = Command('docker bilud -t foo .', '')
    assert get_history_correction(command) is None


def test_prefilter_caps_and_orders_candidates():
    script = 'docker build -t foo . 3'
    lines = ['docker build -t foo . {}'.format(index)
             for index in range(_CANDIDATES + 5)]
    selected = _prefilter(script, lines)
    assert len(selected) == _CANDIDATES
    assert selected[0] == 'docker build -t foo . 3'
