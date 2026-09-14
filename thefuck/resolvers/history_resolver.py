"""History-similarity resolver with correction-only auto-run gates.

Corrects a failed script from a structurally-aligned history command
when exactly one candidate differs only in tokens that each pass a
length-scaled similarity floor (`typo.floor_ok`); anything looser or
ambiguous is declined so the existing `history` rule keeps offering
choices instead of auto-running.
"""
import difflib

from thefuck import shell_ast, typo
from thefuck.utils import get_valid_history_without_current

_PREFILTER_CUTOFF = 0.5
_CANDIDATES = 10


def get_history_correction(command):
    """Returns the corrected script for `command`, or None.

    :type command: thefuck.types.Command
    :rtype: str | None

    """
    candidates = _prefilter(command.script,
                            get_valid_history_without_current(command))
    if not candidates:
        return None
    segments = shell_ast.parse(command.script)
    matches = []
    for candidate in candidates:
        correction = _correct(command.script, segments, candidate)
        if correction is not None:
            matches.append(correction)
            if len(matches) > 1:
                return None
    return matches[0] if len(matches) == 1 else None


def _prefilter(script, history):
    """Returns up to `_CANDIDATES` distinct closest history lines.

    Duplicate lines collapse into one candidate: repeats of the same
    command in history are one option, not ambiguity.
    """
    scored = []
    seen = set()
    for line in history:
        if line in seen:
            continue
        seen.add(line)
        ratio = difflib.SequenceMatcher(None, script, line).ratio()
        if ratio >= _PREFILTER_CUTOFF:
            scored.append((ratio, line))
    scored.sort(key=lambda scored_line: scored_line[0], reverse=True)
    return [line for _, line in scored[:_CANDIDATES]]


def _correct(script, segments, candidate):
    """Returns the spliced correction when candidate passes every gate.

    The gates: identical segment and per-segment token counts, every
    diverged token pair similar enough (length-scaled floor, see
    `typo.floor_ok` — diverged tokens are gated per-token, not
    counted), and a candidate different from the script itself.
    """
    if candidate == script:
        return None
    candidate_segments = shell_ast.parse(candidate)
    if len(candidate_segments) != len(segments):
        return None
    replacements = []
    for segment, candidate_segment in zip(segments, candidate_segments):
        if len(segment.words) != len(candidate_segment.words):
            return None
        for word, candidate_word in zip(segment.words,
                                        candidate_segment.words):
            token, start, end = word
            candidate_token = candidate_word[0]
            if token == candidate_token:
                continue
            if not typo.floor_ok(token, candidate_token):
                return None
            replacements.append((start, end, candidate_token))
    if not replacements:
        # A whitespace-only difference yields no replacements and a
        # correction equal to the script would be a no-op run.
        return None
    return shell_ast.splice(script, replacements)
