import pytest
from mock import Mock

from thefuck import compose
from thefuck.types import Command


@pytest.fixture
def src(monkeypatch):
    """Scripts per-source results and records every consultation.

    A source's scripted entry is a constant candidate, None, or a
    callable mapping the consulted script to a candidate (for
    input-aware tests). `calls` keeps (source, input-script) pairs in
    consultation order; `commands` keeps every Command handed to the
    two output-aware sources.
    """
    state = {
        "learned": None,
        "error-suggestion": None,
        "history": None,
        "path": None,
        "help": None,
        "calls": [],
        "commands": [],
    }
    fake_danger = Mock()
    fake_danger.is_dangerous.return_value = False
    monkeypatch.setattr(compose, "danger", fake_danger)
    state["danger"] = fake_danger

    def _scripted(name, script):
        scripted = state[name]
        if callable(scripted):
            return scripted(script)
        return scripted

    def _script_source(name):
        def fake(script):
            state["calls"].append((name, script))
            return _scripted(name, script)
        return fake

    def _command_source(name):
        def fake(command):
            state["calls"].append((name, command.script))
            state["commands"].append(command)
            return _scripted(name, command.script)
        return fake

    monkeypatch.setattr(compose, "get_correction",
                        _script_source("learned"))
    monkeypatch.setattr(compose, "get_suggestion_candidates",
                        _command_source("error-suggestion"))
    monkeypatch.setattr(compose, "get_history_correction",
                        _command_source("history"))
    monkeypatch.setattr(compose, "guess_from_path",
                        _script_source("path"))
    monkeypatch.setattr(compose, "get_help_correction",
                        _script_source("help"))
    return state


class TestComposition(object):
    def test_two_rounds_compose_into_one_script(self, src):
        src["path"] = lambda script: (
            "git psuh" if script == "gti psuh" else None)
        src["history"] = (
            lambda script: "git push" if script == "git psuh" else None)
        final, steps = compose.resolve(Command("gti psuh", "git output"))
        assert final == "git push"
        assert steps == [("path", "git psuh"), ("history", "git push")]

    def test_first_safe_source_wins_the_round(self, src):
        src["learned"] = "git push"
        src["history"] = "git commit"
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final == "git push"
        assert steps == [("learned", "git push")]

    def test_chain_stops_when_candidate_is_stable(self, src):
        src["history"] = "git push"
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final == "git push"
        assert steps == [("history", "git push")]

    def test_three_round_chain_without_cap(self, src):
        src["history"] = lambda script: {
            "aa bb": "ab bb", "ab bb": "ac bb"}.get(script)
        final, steps = compose.resolve(Command("aa bb", ""))
        assert final == "ac bb"
        assert steps == [("history", "ab bb"), ("history", "ac bb")]


class TestNoAutoRunOfOriginal(object):
    def test_round1_no_candidate_returns_none(self, src):
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final is None
        assert steps == []
        assert src["calls"] == [
            ("learned", "gti psuh"),
            ("error-suggestion", "gti psuh"),
            ("history", "gti psuh"),
            ("path", "gti psuh"),
            ("help", "gti psuh"),
        ]

    def test_round1_candidate_equal_to_original_returns_none(self, src):
        src["path"] = "gti psuh"
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final is None
        assert steps == []

    def test_empty_script_declined_not_echoed(self, src):
        final, steps = compose.resolve(Command("", ""))
        assert final is None
        assert steps == []
        assert src["calls"][0] == ("learned", "")


class TestAbort(object):
    def test_cycle_between_two_scripts_aborts(self, src):
        src["history"] = lambda script: {
            "alpha": "beta", "beta": "alpha"}[script]
        final, steps = compose.resolve(Command("alpha", ""))
        assert final is None
        assert steps == [("history", "beta")]

    def test_original_reentry_in_round2_aborts(self, src):
        src["path"] = "beta"
        src["history"] = lambda script: (
            "alpha" if script == "beta" else None)
        final, steps = compose.resolve(Command("alpha", ""))
        assert final is None
        assert steps == [("path", "beta")]


class TestSourceInputs(object):
    def test_output_sources_get_synthesized_commands(self, src):
        command = Command("gti psuh", "suggestion output")
        src["path"] = lambda script: (
            "git psuh" if script == "gti psuh" else None)
        src["history"] = (
            lambda script: "git push" if script == "git psuh" else None)
        final, _ = compose.resolve(command)
        assert final == "git push"
        # Per round, both output-aware sources see the round's script:
        # original, round-1 composite, round-2 composite (all decline).
        assert src["commands"] == [
            Command("gti psuh", "suggestion output"),
            Command("gti psuh", "suggestion output"),
            Command("git psuh", "suggestion output"),
            Command("git psuh", "suggestion output"),
            Command("git push", "suggestion output"),
            Command("git push", "suggestion output"),
        ]

    def test_script_sources_get_bare_strings(self, src, monkeypatch):
        calls = []

        def fake_guess(script):
            calls.append(("path", script))
            assert not isinstance(script, Command)
            return None
        monkeypatch.setattr(compose, "guess_from_path", fake_guess)
        compose.resolve(Command("gti psuh", ""))
        assert calls == [("path", "gti psuh")]


class TestDangerDecline(object):
    def test_dangerous_candidate_skipped_next_source_wins(self, src):
        src["learned"] = "rm -rf /"
        src["danger"].is_dangerous.side_effect = (
            lambda script: script == "rm -rf /")
        src["path"] = "git push"
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final == "git push"
        assert steps == [("path", "git push")]

    def test_only_dangerous_candidates_declined(self, src):
        src["learned"] = "rm -rf /"
        src["danger"].is_dangerous.return_value = True
        final, steps = compose.resolve(Command("gti psuh", ""))
        assert final is None
        assert steps == []


class TestMemoTripwire(object):
    def test_no_source_input_ever_repeats(self, src):
        # Every accepted candidate is a new node, so no (source,
        # script) pair is consulted twice; the composer's internal
        # memo assert stays silent across a long chain.
        src["history"] = lambda script: {
            "aaaa": "aaab", "aaab": "aabb",
            "aabb": "abbb", "abbb": "bbbb"}.get(script)
        final, steps = compose.resolve(Command("aaaa", ""))
        assert final == "bbbb"
        assert len(steps) == 4
        assert len(src["calls"]) == len(set(src["calls"]))
