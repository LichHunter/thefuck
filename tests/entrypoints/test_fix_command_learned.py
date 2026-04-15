import pytest
from mock import Mock, patch, call
from thefuck.entrypoints.fix_command import fix_command
from thefuck.types import CorrectedCommand


@pytest.fixture
def mock_learned(monkeypatch):
    state = {"correction": None, "recordings": []}

    def fake_get_correction(script):
        return state["correction"]

    def fake_record(original, corrected):
        state["recordings"].append((original, corrected))

    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.get_correction", fake_get_correction
    )
    monkeypatch.setattr("thefuck.entrypoints.fix_command.record", fake_record)
    return state


@pytest.fixture
def known_args():
    return Mock(
        force_command="git psuh origin main", yes=False, debug=False, repeat=False
    )


class TestLearnedAutoApply(object):
    def test_auto_applies_learned_correction(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = "git push origin main"
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", lambda _: iter([])
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", lambda _: None
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)
            mock_run.assert_called_once()

    def test_learned_skips_rule_matching(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = "git push origin main"
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)
            get_corrected.assert_not_called()

    def test_shows_corrected_command_on_auto_apply(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = "git push origin main"

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            assert mock_show.call_count == 1
            shown_cmd = mock_show.call_args[0][0]
            assert shown_cmd.script == "git push origin main"


class TestRecordOnSelection(object):
    def test_records_user_selection(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        selected = CorrectedCommand(
            script="git push origin main", side_effect=None, priority=100
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([selected]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", lambda _: selected
        )

        with patch("thefuck.types.CorrectedCommand.run"):
            fix_command(known_args)
            assert mock_learned["recordings"] == [
                ("git psuh origin main", "git push origin main")
            ]

    def test_does_not_record_on_abort(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", lambda _: iter([])
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", lambda _: None
        )

        with pytest.raises(SystemExit):
            fix_command(known_args)
        assert mock_learned["recordings"] == []


class TestFallthrough(object):
    def test_falls_through_to_rules_when_no_learned(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        selected = CorrectedCommand(
            script="git push origin main", side_effect=None, priority=100
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([selected]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", lambda _: selected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run:
            fix_command(known_args)
            mock_run.assert_called_once()
