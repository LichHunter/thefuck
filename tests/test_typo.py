from difflib import SequenceMatcher

from thefuck.typo import floor_ok, single_edit

_LEN30 = 'abcdefghijklmnopqrstuvwxyz0123'


class TestSubstitution(object):
    def test_single_substitution(self):
        assert single_edit('greo', 'grep')

    def test_single_substitution_one_char_words(self):
        assert single_edit('a', 'b')


class TestTransposition(object):
    def test_adjacent_transposition_gti(self):
        assert single_edit('gti', 'git')

    def test_adjacent_transposition_psuh(self):
        assert single_edit('psuh', 'push')

    def test_adjacent_transposition_bulid(self):
        assert single_edit('bulid', 'build')

    def test_transposition_is_symmetric(self):
        assert single_edit('git', 'gti')

    def test_non_adjacent_swap_is_two_edits(self):
        # Swapping two NON-adjacent characters takes two moves:
        # abcd -> badc diverges at every position.
        assert not single_edit('abcd', 'badc')

    def test_two_differing_positions_not_crossed(self):
        # Two substitutions shaped like a swap but with distinct
        # characters are two edits, not one transposition.
        assert not single_edit('ab', 'cd')


class TestInsertionAndDeletion(object):
    def test_single_insertion(self):
        assert single_edit('clea', 'clear')

    def test_single_deletion(self):
        assert single_edit('clear', 'clea')

    def test_insertion_in_the_middle(self):
        assert single_edit('gt', 'git')

    def test_two_insertions(self):
        assert not single_edit('cl', 'clear')


class TestBoundaries(object):
    def test_equal_strings(self):
        assert not single_edit('git', 'git')

    def test_empty_strings(self):
        assert not single_edit('', '')

    def test_empty_to_single_char(self):
        assert single_edit('', 'a')

    def test_single_char_to_empty(self):
        assert single_edit('a', '')

    def test_empty_to_two_chars(self):
        assert not single_edit('', 'ab')

    def test_length_difference_over_one(self):
        assert not single_edit('g', 'git')

    def test_shifted_words_are_two_edits(self):
        # abc -> bcd keeps no common alignment: a deletion plus an
        # insertion, i.e. two edits.
        assert not single_edit('abc', 'bcd')

    def test_two_substitutions(self):
        # Adjacent but not crossed: two substitutions, not one
        # transposition.
        assert not single_edit('abcd', 'abxy')

    def test_help_flag_boundary_pair(self):
        # The pair the history-resolver boundary test pins: under the
        # 0.8 ratio cutoff (0.769) AND not a single edit, so the
        # amended gate still declines it.
        assert not single_edit('--ignore-whitespaces',
                               '--ignore-all-spaces')


class TestFloorOk(object):
    def test_len3_floor_passes(self):
        # max length 3 -> floor max(0.6, 1 - 3/3) = 0.6; the plain
        # substitution scores 2 * 2 / 6 = 0.667.
        assert SequenceMatcher(None, 'abc', 'abz').ratio() >= 0.6
        assert floor_ok('abc', 'abz')

    def test_len3_below_floor_declines(self):
        # Two substitutions score 0.333, under the 0.6 floor.
        assert SequenceMatcher(None, 'axx', 'ayy').ratio() < 0.6
        assert not floor_ok('axx', 'ayy')

    def test_len10_floor_passes(self):
        # max length 10 -> floor 1 - 3/10 = 0.7; three trailing
        # substitutions keep 7 matches: exactly 2 * 7 / 20 = 0.7.
        assert SequenceMatcher(
            None, 'abcdefghij', 'abcdefgxyz').ratio() >= 0.7
        assert floor_ok('abcdefghij', 'abcdefgxyz')

    def test_len10_below_floor_declines(self):
        # Four trailing substitutions score 0.6, under 0.7.
        assert SequenceMatcher(
            None, 'abcdefghij', 'abcdefwxyz').ratio() < 0.7
        assert not floor_ok('abcdefghij', 'abcdefwxyz')

    def test_len30_floor_passes(self):
        # max length 30 -> floor 1 - 3/30 = 0.9; three trailing
        # substitutions keep 27 matches: exactly 2 * 27 / 60 = 0.9.
        assert SequenceMatcher(
            None, _LEN30, _LEN30[:27] + '456').ratio() >= 0.9
        assert floor_ok(_LEN30, _LEN30[:27] + '456')

    def test_len30_below_floor_declines(self):
        # Four trailing substitutions score ~0.867, under 0.9.
        assert SequenceMatcher(
            None, _LEN30, _LEN30[:26] + '4567').ratio() < 0.9
        assert not floor_ok(_LEN30, _LEN30[:26] + '4567')

    def test_single_edit_always_passes(self):
        assert floor_ok('gti', 'git')
        assert floor_ok('psuh', 'push')
        assert floor_ok('clea', 'clear')
        assert floor_ok('clear', 'clea')

    def test_first_char_mismatch_always_fails(self):
        # The first-letter guard holds for the ratio path and the
        # single-edit path alike.
        assert SequenceMatcher(None, 'abcd', 'zbcd').ratio() >= 0.6
        assert not floor_ok('abcd', 'zbcd')
        assert single_edit('abz', 'bbz')
        assert not floor_ok('abz', 'bbz')
        assert not floor_ok('ls', 'sl')
