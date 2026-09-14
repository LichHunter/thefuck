"""Fixpoint composition of the auto-run correction sources.

Consults the learned db, the failing binary's own suggestions,
history, $PATH guesses and `--help` in a fixed order, applying each
round's accepted correction to the previous round's script until the
result is stable, revisits a script (cycle) or no source has a safe
candidate left. Only the final composite is returned for running.

Interface contract for sources (termination rests on it): every
source MUST return either a string drawn from a finite fixed range
(learned-db entries, history lines, help/suggestion lists,
executables on $PATH) or a word-count-preserving splice of its input
script — the reachable script space is then finite (finite
vocabulary, bounded word count), so the chain cannot grow forever.
A source that APPENDS to or otherwise grows scripts unboundedly
would break termination and is FORBIDDEN. Cycles cannot loop: any
revisit of an already-seen script hits the visited-set and aborts
the composition.

Personal fork only: depends on bashlex (GPL-3+), do not distribute.
"""
from . import danger, logs, types
from .learned import get_correction, guess_from_path
from .resolvers.error_suggestion import get_suggestion_candidates
from .resolvers.help_resolver import get_help_correction
from .resolvers.history_resolver import get_history_correction

LEARNED_SOURCE = 'learned'


def resolve(command):
    """Composes corrections from the sources into one fixed script.

    Returns `(final_script, steps)` where `steps` holds one
    `(source, script)` pair per accepted round, or `(None, steps)`
    when nothing was accepted — round one yielding no candidate or a
    candidate equal to the original — so the caller falls back to
    rules and asking: the original failing script is never
    auto-run. A candidate revisiting an already-seen script aborts
    the same way, with the steps accepted before the revisit.

    :type command: thefuck.types.Command
    :rtype: (str | None, [(str, str)])
    """
    current = command.script
    visited = set([current])
    steps = []
    memo = {}
    while True:
        name, candidate = _round(command, current, memo)
        if name is None:
            break
        if candidate == current:
            logs.debug(u'Correction stable at: {}'.format(candidate))
            break
        if candidate in visited:
            logs.debug(u'Correction cycles back to {}, aborting'
                       .format(candidate))
            return None, steps
        visited.add(candidate)
        steps.append((name, candidate))
        current = candidate
    if not steps:
        return None, steps
    return current, steps


def _round(command, script, memo):
    """Consults every source in order against `script`.

    Returns the first `(name, candidate)` whose candidate passes the
    danger check (dangerous candidates are declined for auto-run and
    consultation continues), or `(None, None)` when every source
    declines. `memo` is a determinism tripwire, not the termination
    guarantee: inputs never repeat within one resolve because every
    accepted candidate is a new node, so a `(source, script)` hit in
    the memo means a source or the loop broke that invariant.
    """
    for name, consult in _sources():
        key = (name, script)
        assert key not in memo, (
            u'tripwire: {} consulted twice with {!r}'.format(name, script))
        candidate = consult(command, script)
        memo[key] = candidate
        if candidate is None:
            continue
        if danger.is_dangerous(candidate):
            logs.debug(u'Declining dangerous candidate from {}: {}'
                       .format(name, candidate))
            continue
        return name, candidate
    return None, None


def _sources():
    """The auto-run sources in consultation order.

    Each adapter maps `(command, script)` to a candidate script or
    None; the two output-aware resolvers get a synthesized
    `types.Command` wrapping the round's script with the original
    failure's output, so later rounds still see what went wrong.
    """
    return (
        (LEARNED_SOURCE, lambda command, script: get_correction(script)),
        ('error-suggestion', _suggestion),
        ('history', lambda command, script: get_history_correction(
            types.Command(script=script, output=command.output))),
        ('path', lambda command, script: guess_from_path(script)),
        ('help', lambda command, script: get_help_correction(script)),
    )


def _suggestion(command, script):
    # The failing output is only readable while it exists; a timed-out
    # rerun has None and nothing can be extracted from it.
    if command.output is None:
        return None
    return get_suggestion_candidates(
        types.Command(script=script, output=command.output))
