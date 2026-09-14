import pytest

from thefuck import shell_ast
from thefuck.learned import LearnedCorrections


@pytest.fixture
def learned(tmp_path):
    lc = LearnedCorrections()
    lc._db = {}
    return lc


class TestRecord(object):
    def test_noop_when_scripts_identical(self, learned):
        learned.record("git push", "git push")
        assert len(learned.db) == 0

    def test_stores_full_command_mapping(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        assert (
            learned.db["cmd:git psuh origin main"]["corrected"]
            == "git push origin main"
        )

    def test_increments_count_on_repeat(self, learned):
        learned.record("git psuh", "git push")
        learned.record("git psuh", "git push")
        assert learned.db["cmd:git psuh"]["count"] == 2

    def test_updates_timestamp(self, learned):
        learned.record("git psuh", "git push")
        first_ts = learned.db["cmd:git psuh"]["timestamp"]
        learned.record("git psuh", "git push")
        assert learned.db["cmd:git psuh"]["timestamp"] >= first_ts

    def test_stores_command_word_replacement(self, learned):
        learned.record("pyhton script.py", "python script.py")
        assert learned.db["word:pyhton"]["replacement"] == "python"

    def test_stores_subcommand_replacement(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        assert learned.db["part:git:psuh"]["replacement"] == "push"

    def test_stores_multiple_word_diffs(self, learned):
        learned.record("gti comit -m msg", "git commit -m msg")
        assert learned.db["word:gti"]["replacement"] == "git"
        assert learned.db["part:git:comit"]["replacement"] == "commit"

    def test_no_word_level_when_lengths_differ(self, learned):
        learned.record("git push", "git push --set-upstream origin main")
        assert "cmd:git push" in learned.db
        assert not any(
            k.startswith("word:") or k.startswith("part:") for k in learned.db
        )

    def test_updates_correction_on_changed_choice(self, learned):
        learned.record("apt install vim", "sudo apt install vim")
        learned.record("apt install vim", "apt-get install vim")
        assert learned.db["cmd:apt install vim"]["corrected"] == "apt-get install vim"
        assert learned.db["cmd:apt install vim"]["count"] == 2


class TestGetCorrection(object):
    def test_exact_full_command_match(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        assert learned.get_correction("git psuh origin main") == "git push origin main"

    def test_generalises_subcommand_to_different_args(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        assert learned.get_correction("git psuh origin dev") == "git push origin dev"

    def test_generalises_command_word(self, learned):
        learned.record("pyhton script.py", "python script.py")
        assert learned.get_correction("pyhton other.py") == "python other.py"

    def test_combined_command_and_subcommand(self, learned):
        learned.record("gti comit -m msg", "git commit -m msg")
        assert learned.get_correction('gti comit -m "other"') == 'git commit -m "other"'

    def test_returns_none_when_no_match(self, learned):
        assert learned.get_correction("totally unknown cmd") is None

    def test_returns_none_for_empty_script(self, learned):
        assert learned.get_correction("") is None

    def test_prefers_full_command_over_word_level(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        learned.db["cmd:git psuh origin main"]["corrected"] = (
            "git push --force origin main"
        )
        assert (
            learned.get_correction("git psuh origin main")
            == "git push --force origin main"
        )

    def test_word_level_only_replaces_known_tokens(self, learned):
        learned.record("git psuh origin main", "git push origin main")
        result = learned.get_correction("git psuh origin dev")
        assert result == "git push origin dev"

    def test_cross_resolve_command_and_part(self, learned):
        """When both cmd word and subcommand are typos, parts stored
        under the corrected cmd name still resolve."""
        learned.record("gti psuh origin main", "git push origin main")
        assert learned.get_correction("gti psuh origin dev") == "git push origin dev"

    def test_single_word_command(self, learned):
        learned.record("sl", "ls")
        assert learned.get_correction("sl") == "ls"


class TestGuessFromPath(object):
    @pytest.fixture
    def path_bins(self, monkeypatch):
        def setup(executables, existing=()):
            monkeypatch.setattr('thefuck.learned.get_all_executables',
                                lambda: list(executables))
            monkeypatch.setattr('thefuck.learned.which',
                                lambda token: token in existing)
        return setup

    def test_guesses_unique_close_match(self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert learned.guess_from_path('cler') == 'clear'

    def test_keeps_arguments(self, learned, path_bins):
        path_bins(executables=['python', 'pydoc', 'grep'])
        assert (learned.guess_from_path('pyhton script.py')
                == 'python script.py')

    def test_returns_none_when_ambiguous(self, learned, path_bins):
        path_bins(executables=['clear', 'clean'])
        assert learned.guess_from_path('clea') is None

    def test_returns_none_when_token_is_executable(self, learned, path_bins):
        path_bins(executables=['clear'], existing=['clear'])
        assert learned.guess_from_path('clear') is None

    def test_returns_none_for_path_like_token(self, learned, path_bins):
        path_bins(executables=['git', 'grep', 'sed'])
        assert learned.guess_from_path('./gti push') is None

    def test_returns_none_for_token_with_extension(self, learned, path_bins):
        path_bins(executables=['git', 'grep', 'sed'])
        assert learned.guess_from_path('giti.py x') is None

    def test_returns_none_when_first_char_differs(self, learned, path_bins):
        path_bins(executables=['top'])
        assert learned.guess_from_path('htop') is None

    def test_returns_none_below_length_scaled_floor(self, learned,
                                                    path_bins):
        # 10-char token vs executable sharing only the 6 leading
        # chars scores 2 * 6 / 20 = 0.6, under the len-10 floor 0.7,
        # and the pair is not a single edit.
        path_bins(executables=['burnnoabcd'])
        assert learned.guess_from_path('burnno1234 file') is None

    def test_guesses_via_ratio_above_scaled_floor(self, learned,
                                                  path_bins):
        # Three trailing substitutions score exactly the len-10
        # floor 0.7 — a pair the old fixed 0.8 cutoff declined — and
        # no other executable shares the first char, so the ratio
        # path alone admits the match.
        path_bins(executables=['abcdefgxyz', 'grep', 'sed'])
        assert (learned.guess_from_path('abcdefghij file')
                == 'abcdefgxyz file')

    def test_guesses_after_sudo(self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert learned.guess_from_path('sudo cler') == 'sudo clear'

    def test_returns_none_for_empty_script(self, learned, path_bins):
        path_bins(executables=['git'])
        assert learned.guess_from_path('') is None


class TestGuessFromPathSegments(object):
    pytestmark = pytest.mark.skipif(
        not shell_ast.AST_AVAILABLE, reason='bashlex required')

    @pytest.fixture
    def path_bins(self, monkeypatch):
        def setup(executables, existing=()):
            monkeypatch.setattr('thefuck.learned.get_all_executables',
                                lambda: list(executables))
            monkeypatch.setattr('thefuck.learned.which',
                                lambda token: token in existing)
        return setup

    def test_fixes_head_of_every_pipe_segment(self, learned, path_bins):
        path_bins(executables=['git', 'grep', 'sed'])
        assert (learned.guess_from_path('gi psuh | gre -i foo')
                == 'git psuh | grep -i foo')

    def test_fixes_single_edit_typos(self, learned, path_bins):
        # gti -> git scores 2 * 2 / 6 = 0.667 and greo -> grep scores
        # 2 * 3 / 8 = 0.75; each is a first-char-equal single edit
        # with one executable match.
        path_bins(executables=['git', 'grep', 'sed'])
        assert (learned.guess_from_path('gti psuh | greo -i foo')
                == 'git psuh | grep -i foo')

    def test_declines_single_edit_ambiguity(self, learned, path_bins):
        # gti is one edit from both git (transposition) and gui
        # (substitution), each scoring 2 * 2 / 6 = 0.667, so two
        # candidates survive and the segment is skipped.
        path_bins(executables=['git', 'gui'])
        assert learned.guess_from_path('gti psuh') is None

    def test_fixes_only_segment_with_unknown_head(self, learned, path_bins):
        path_bins(executables=['git', 'grep', 'sed'], existing=['git'])
        assert (learned.guess_from_path('git psuh | gre -i foo')
                == 'git psuh | grep -i foo')

    def test_returns_none_when_all_heads_executable(self, learned, path_bins):
        path_bins(executables=['git', 'grep'], existing=['git', 'grep'])
        assert learned.guess_from_path('git psuh | grep -i foo') is None

    def test_skips_ambiguous_segment_fixes_others(self, learned, path_bins):
        path_bins(executables=['clear', 'clean', 'grep'])
        assert (learned.guess_from_path('clea psuh | gre -i foo')
                == 'clea psuh | grep -i foo')

    def test_guesses_after_sudo_in_pipe(self, learned, path_bins):
        path_bins(executables=['clear', 'grep'])
        assert (learned.guess_from_path('sudo cler | gre -i foo')
                == 'sudo clear | grep -i foo')

    def test_guesses_after_sudo_flat(self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert learned.guess_from_path('sudo cler') == 'sudo clear'

    def test_replaces_quoted_head_whole(self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert learned.guess_from_path('"cler" psuh') == 'clear psuh'

    def test_preserves_spacing_between_words(self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert learned.guess_from_path('cler  psuh') == 'clear  psuh'

    def test_unparseable_script_falls_back_to_flat_view(
            self, learned, path_bins):
        path_bins(executables=['clear', 'grep', 'sed'])
        assert (
            learned.guess_from_path('cler psuh; case $x in y) ;; esac')
            == 'clear psuh; case $x in y) ;; esac')


class TestClear(object):
    def test_removes_all_entries(self, learned):
        learned.record("git psuh", "git push")
        learned.record("pyhton x.py", "python x.py")
        learned.clear()
        assert len(learned.db) == 0

    def test_no_matches_after_clear(self, learned):
        learned.record("git psuh", "git push")
        learned.clear()
        assert learned.get_correction("git psuh") is None


class TestRoundTrip(object):
    def test_record_then_match(self, learned):
        learned.record("docker bilud .", "docker build .")
        assert learned.get_correction("docker bilud .") == "docker build ."

    def test_record_then_generalise(self, learned):
        learned.record("docker bilud -t foo .", "docker build -t foo .")
        assert (
            learned.get_correction("docker bilud -t bar .") == "docker build -t bar ."
        )

    def test_multiple_distinct_commands(self, learned):
        learned.record("git psuh", "git push")
        learned.record("pyhton x.py", "python x.py")
        assert learned.get_correction("git psuh") == "git push"
        assert learned.get_correction("pyhton y.py") == "python y.py"
