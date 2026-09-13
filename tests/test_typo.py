from thefuck.typo import single_edit


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
