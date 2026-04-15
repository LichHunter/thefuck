import pytest
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
