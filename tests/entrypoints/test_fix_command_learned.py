import pytest
from mock import Mock, patch
from thefuck import danger as real_danger
from thefuck.entrypoints.fix_command import fix_command
from thefuck.shells import Nushell
from thefuck.types import Command, CorrectedCommand

ORIGINAL = "git psuh origin main"
CORRECTED = "git push origin main"


@pytest.fixture
def mock_learned(monkeypatch):
    state = {"correction": None, "suggestion": None, "history": None,
             "guess": None, "help": None, "recordings": [], "calls": [],
             "forgets": [], "order": [], "closes": 0}
    # The real gate fail-safes to True without bashlex, which would
    # make every auto-apply test platform-dependent; the danger
    # override tests re-install the real module in both consumers.
    fake_danger = Mock()
    fake_danger.is_dangerous.return_value = False
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.danger", fake_danger
    )
    monkeypatch.setattr("thefuck.compose.danger", fake_danger)

    def scripted(key, script):
        value = state[key]
        if callable(value):
            return value(script)
        # Input-aware: a constant candidate is scripted for the
        # original script only, so round 2 of the composition
        # declines instead of accepting it again.
        return value if script == ORIGINAL else None

    def script_source(key, label):
        def fake(script):
            state["calls"].append(label)
            return scripted(key, script)
        return fake

    def command_source(key, label):
        def fake(command):
            state["calls"].append(label)
            return scripted(key, command.script)
        return fake

    def fake_record(original, corrected):
        state["order"].append("record")
        state["recordings"].append((original, corrected))

    def fake_forget(original, corrected):
        state["order"].append("forget")
        state["forgets"].append((original, corrected))

    def fake_close_db():
        state["order"].append("close")
        state["closes"] += 1

    monkeypatch.setattr(
        "thefuck.compose.get_correction",
        script_source("correction", "learned")
    )
    monkeypatch.setattr(
        "thefuck.compose.get_suggestion_candidates",
        command_source("suggestion", "error-suggestion")
    )
    monkeypatch.setattr(
        "thefuck.compose.get_history_correction",
        command_source("history", "history")
    )
    monkeypatch.setattr(
        "thefuck.compose.guess_from_path", script_source("guess", "path")
    )
    monkeypatch.setattr(
        "thefuck.compose.get_help_correction", script_source("help", "help")
    )
    fake_learned = Mock(record=fake_record, forget=fake_forget,
                        close_db=fake_close_db)
    monkeypatch.setattr(
        "thefuck.entrypoints.fix_command.learned", fake_learned
    )
    return state


@pytest.fixture
def known_args():
    return Mock(
        force_command="git psuh origin main", yes=False, debug=False,
        repeat=False
    )


class TestLearnedAutoApply(object):
    def test_auto_applies_learned_correction(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = CORRECTED
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([])
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
        mock_learned["correction"] = CORRECTED
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)
            get_corrected.assert_not_called()

    def test_shows_corrected_command_on_auto_apply(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            assert mock_show.call_count == 1
            shown_cmd = mock_show.call_args[0][0]
            assert shown_cmd.script == CORRECTED


class TestGuessAutoApply(object):
    def test_guess_records_and_auto_applies(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["guess"] = CORRECTED
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)
            mock_run.assert_called_once()
            get_corrected.assert_not_called()
            assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]

    def test_exact_learned_wins_over_guess(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = "git push origin dev"
        mock_learned["guess"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            shown_cmd = mock_show.call_args[0][0]
            assert shown_cmd.script == "git push origin dev"
            assert mock_learned["recordings"] == []


class TestResolverChainOrder(object):
    # Round 1 consults [learned, error-suggestion, history, path,
    # help] up to the round's winner; round 2 consults all five with
    # the corrected script, the input-aware fakes decline and the
    # composition ends at a stable point.
    def test_full_chain_consulted_in_order_when_only_help_hits(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["help"] = CORRECTED
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run"), patch(
            "thefuck.logs.show_corrected_command"
        ):
            fix_command(known_args)

        assert mock_learned["calls"] == [
            "learned", "error-suggestion", "history", "path", "help",
            "learned", "error-suggestion", "history", "path", "help",
        ]
        get_corrected.assert_not_called()

    @pytest.mark.parametrize("hit_source,expected_calls", [
        ("history", ["learned", "error-suggestion", "history",
                     "learned", "error-suggestion", "history",
                     "path", "help"]),
        ("guess", ["learned", "error-suggestion", "history", "path",
                   "learned", "error-suggestion", "history", "path",
                   "help"]),
    ])
    def test_earlier_hit_stops_the_round(
        self, mock_learned, known_args, settings, monkeypatch, hit_source,
        expected_calls
    ):
        mock_learned[hit_source] = CORRECTED

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
            "thefuck.compose.get_history_correction", history_mock
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
        assert history_mock.call_args[0][0].script == ORIGINAL


class TestResolverAutoApply(object):
    @pytest.mark.parametrize("source", ["history", "help"])
    def test_resolver_hit_records_and_auto_applies(
        self, mock_learned, known_args, settings, monkeypatch, source
    ):
        mock_learned[source] = CORRECTED
        get_corrected = Mock()
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            get_corrected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            mock_run.assert_called_once()
            get_corrected.assert_not_called()
            assert mock_show.call_args[0][0].script == CORRECTED
            assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]


class TestComposition(object):
    def test_two_sources_compose_into_one_run(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["guess"] = "git psuh origin main"
        mock_learned["history"] = (
            lambda script: CORRECTED if script == "git psuh origin main"
            else None)

        with patch("thefuck.types.CorrectedCommand.run") as mock_run, patch(
            "thefuck.logs.show_corrected_command"
        ) as mock_show:
            fix_command(known_args)
            mock_run.assert_called_once()
            assert mock_show.call_args[0][0].script == CORRECTED
            assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]


class TestDangerOverride(object):
    @pytest.mark.parametrize(
        "hit_source",
        ["correction", "suggestion", "history", "guess", "help"])
    def test_dangerous_hit_asks_instead_of_auto_running(
        self, mock_learned, known_args, settings, monkeypatch, hit_source
    ):
        # The real gate: a danger-flagged candidate from ANY source —
        # a seeded learned-db exact hit included — is declined by the
        # composer, falls to select_command and nothing auto-runs. The
        # abort via the mocked selection keeps the pin free of
        # terminal IO.
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.danger", real_danger
        )
        monkeypatch.setattr("thefuck.compose.danger", real_danger)
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
            script=CORRECTED, side_effect=None, priority=100
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([selected]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command",
            lambda _: selected
        )

        with patch("thefuck.types.CorrectedCommand.run"):
            fix_command(known_args)
            assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]

    def test_does_not_record_on_abort(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([])
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
            script=CORRECTED, side_effect=None, priority=100
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.get_corrected_commands",
            lambda _: iter([selected]),
        )
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.select_command",
            lambda _: selected
        )

        with patch("thefuck.types.CorrectedCommand.run") as mock_run:
            fix_command(known_args)
            mock_run.assert_called_once()

    def test_falls_through_to_rules_when_all_resolvers_decline(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        selected = CorrectedCommand(
            script=CORRECTED, side_effect=None, priority=100
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
            "learned", "error-suggestion", "history", "path", "help"
        ]
        assert select.call_count == 1


class TestOutcomeLearning(object):
    @pytest.fixture
    def nushell(self, monkeypatch):
        monkeypatch.setattr(
            "thefuck.entrypoints.fix_command.shell", Nushell())

    def _run_with_returncode(self, order, returncode):
        def run(cmd_self, old_cmd):
            order.append("run")
            cmd_self.returncode = returncode
        return run

    def test_success_records_after_run(
        self, mock_learned, known_args, settings, monkeypatch, nushell
    ):
        mock_learned["guess"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 0)
            fix_command(known_args)

        assert mock_learned["order"] == ["close", "run", "record"]
        assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]
        assert mock_learned["forgets"] == []

    def test_failure_forgets_after_run(
        self, mock_learned, known_args, settings, monkeypatch, nushell
    ):
        mock_learned["guess"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 1)
            fix_command(known_args)

        assert mock_learned["order"] == ["close", "run", "forget"]
        assert mock_learned["forgets"] == [(ORIGINAL, CORRECTED)]
        assert mock_learned["recordings"] == []

    def test_learned_replay_failure_still_forgets(
        self, mock_learned, known_args, settings, monkeypatch, nushell
    ):
        # Poison self-heal: a seeded exact hit that fails on rerun is
        # removed, so the no-rerecord carve-out must not skip the
        # outcome gating.
        mock_learned["correction"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 1)
            fix_command(known_args)

        assert mock_learned["order"] == ["close", "run", "forget"]
        assert mock_learned["forgets"] == [(ORIGINAL, CORRECTED)]

    def test_repeat_records_before_run_without_outcome_gating(
        self, mock_learned, known_args, settings, monkeypatch, nushell
    ):
        known_args.repeat = True
        mock_learned["guess"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 1)
            fix_command(known_args)

        assert mock_learned["order"] == ["record", "run"]
        assert mock_learned["recordings"] == [(ORIGINAL, CORRECTED)]
        assert mock_learned["closes"] == 0

    def test_other_shells_record_before_run(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["guess"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 1)
            fix_command(known_args)

        assert mock_learned["order"] == ["record", "run"]
        assert mock_learned["closes"] == 0

    def test_learned_only_win_does_not_rerecord_on_other_shells(
        self, mock_learned, known_args, settings, monkeypatch
    ):
        mock_learned["correction"] = CORRECTED

        with patch("thefuck.types.CorrectedCommand.run",
                   autospec=True) as mock_run, patch(
                "thefuck.logs.show_corrected_command"):
            mock_run.side_effect = self._run_with_returncode(
                mock_learned["order"], 0)
            fix_command(known_args)

        assert mock_learned["order"] == ["run"]
        assert mock_learned["recordings"] == []


class TestNushellRunStashesReturncode(object):
    def test_run_stashes_nu_returncode_on_the_instance(
        self, settings, monkeypatch
    ):
        settings.alter_history = False
        monkeypatch.setattr("thefuck.types.shell", Nushell())
        completed = Mock(returncode=3)
        with patch("thefuck.types.subprocess.run",
                   return_value=completed) as mock_spawn:
            corrected = CorrectedCommand("git push", None, 0)
            corrected.run(Command("git psuh", ""))
        mock_spawn.assert_called_once_with(["nu", "-c", "git push"])
        assert corrected.returncode == 3
