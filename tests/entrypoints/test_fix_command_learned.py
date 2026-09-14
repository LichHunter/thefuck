import pytest
from mock import Mock, patch
from thefuck import danger as real_danger
from thefuck.entrypoints.fix_command import fix_command
from thefuck.types import CorrectedCommand


@pytest.fixture
def mock_learned(monkeypatch):
    state = {"correction": None, "guess": None, "history": None,
             "help": None, "recordings": [], "calls": []}
    # The real gate fail-safes to True without bashlex, which would
    # make every auto-apply test platform-dependent; the danger
    # override tests re-install the real module.
    fake_danger = Mock()
    fake_danger.is_dangerous.return_value = False
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.danger", fake_danger
    )

    def fake_get_correction(script):
        state["calls"].append("correction")
        return state["correction"]

    def fake_history(command):
        state["calls"].append("history")
        return state["history"]

    def fake_guess(script):
        state["calls"].append("guess")
        return state["guess"]

    def fake_help(script):
        state["calls"].append("help")
        return state["help"]

    def fake_record(original, corrected):
        state["recordings"].append((original, corrected))

    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.get_correction", fake_get_correction
    )
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.get_history_correction", fake_history
    )
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.guess_from_path", fake_guess
    )
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.get_help_correction", fake_help
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


class TestGuessAutoApply(object):
    def test_guess_records_and_auto_applies(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["guess"] = "git push origin main"
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)
            mock_run.assert_called_once()
            get_corrected.assert_not_called()
            assert mock_learned["recordings"] == [
                ("git psuh origin main", "git push origin main")
            ]

    def test_exact_learned_wins_over_guess(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = "git push origin dev"
        mock_learned["guess"] = "git push origin main"

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            shown_cmd = mock_show.call_args[0][0]
            assert shown_cmd.script == "git push origin dev"
            assert mock_learned["recordings"] == []


class TestResolverChainOrder(object):
    def test_full_chain_consulted_in_order_when_only_help_hits(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["help"] = "git push origin main"
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)

        assert mock_learned["calls"] == [
            "correction", "history", "guess", "help"
        ]
        get_corrected.assert_not_called()

    @pytest.mark.parametrize("hit_source,expected_calls", [
        ("history", ["correction", "history"]),
        ("guess", ["correction", "history", "guess"]),
    ])
    def test_earlier_hit_stops_the_chain(
        self, mock_learned, known_args, settings, hit_source, expected_calls
    ):
        mock_learned[hit_source] = "git push origin main"

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)

        assert mock_learned["calls"] == expected_calls

    def test_history_receives_command_object(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        history_mock = Mock(return_value=None)
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_history_correction", history_mock
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", lambda _: None
        )

        with pytest.raises(SystemExit):
            fix_command(known_args)

        assert history_mock.call_count == 1
        assert history_mock.call_args[0][0].script == "git psuh origin main"


class TestResolverAutoApply(object):
    @pytest.mark.parametrize("source", ["history", "help"])
    def test_resolver_hit_records_and_auto_applies(
        self, mock_learned, known_args, settings, monkeypatch, source
    ):
        mock_learned[source] = "git push origin main"
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands", get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            mock_run.assert_called_once()
            get_corrected.assert_not_called()
            assert mock_show.call_args[0][0].script == "git push origin main"
            assert mock_learned["recordings"] == [
                ("git psuh origin main", "git push origin main")
            ]


class TestDangerOverride(object):
    @pytest.mark.parametrize(
        "hit_source", ["correction", "history", "guess", "help"])
    def test_dangerous_hit_asks_instead_of_auto_running(
        self, mock_learned, known_args, settings, monkeypatch, hit_source
    ):
        # The real gate: a danger-flagged candidate from ANY source —
        # a seeded learned-db exact hit included — reaches
        # select_command and nothing auto-runs. The abort via the
        # mocked selection keeps the pin free of terminal IO.
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.danger", real_danger
        )
        mock_learned[hit_source] = "rm -rf /"
        select = Mock(return_value=None)
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", select
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            with pytest.raises(SystemExit):
                fix_command(known_args)

        select.assert_called_once()
        mock_run.assert_not_called()
        mock_show.assert_not_called()


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

    def test_falls_through_to_rules_when_all_resolvers_decline(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        selected = CorrectedCommand(
            script="git push origin main", side_effect=None, priority=100
        )
        select = Mock(return_value=selected)
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([selected]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command", select
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run:
            fix_command(known_args)
            mock_run.assert_called_once()

        assert mock_learned["calls"] == [
            "correction", "history", "guess", "help"
        ]
        assert select.call_count == 1
