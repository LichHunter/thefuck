"""Auto-fixes from the failing binary's own error suggestions.

Trigger: the failed command's output names an offending token
(``'X' is not a ...``, ``Unknown command 'X'``) and then suggests
corrections (``The most similar command ...`` / ``Did you mean ...``).
The token is replaced at the position the binary's error nominates —
head or subcommand — and only when exactly one distinct suggestion
passes the length-scaled typo floor, so ambiguity stays on the ask
path and the `git_not_command`-style rules keep handling the rest.

Personal fork only: depends on bashlex (GPL-3+), do not distribute.
"""
import re

from thefuck import shell_ast, typo
from thefuck.utils import get_all_matched_commands

_SEPARATORS = ['The most similar command', 'Did you mean']

_TOKEN_PATTERNS = (
    re.compile(r"'([^']+)' is not a"),
    re.compile(r"Unknown command '([^']+)'"),
    re.compile(r"unknown command '([^']+)'"),
)


def get_suggestion_candidates(command):
    """Returns the corrected script for `command`, or None.

    :type command: thefuck.types.Command
    :rtype: str | None

    """
    if not shell_ast.AST_AVAILABLE:
        return None
    broken = _offending_token(command.output)
    if broken is None:
        return None
    # A suggestion equal to the token would splice to a no-op run,
    # and duplicates of one command are a single option, not
    # ambiguity (unique-survivor semantics, as in sibling resolvers).
    eligible = set(suggestion for suggestion in _suggestions(command.output)
                   if suggestion != broken
                   and typo.floor_ok(broken, suggestion))
    if len(eligible) != 1:
        return None
    replacement = eligible.pop()
    # First occurrence wins (replace_argument precedent); raw spans
    # keep their quotes, so a quoted token's whole span is replaced.
    for segment in shell_ast.parse(command.script):
        for word, start, end in segment.words:
            if _unquoted(word) == broken:
                return shell_ast.splice(
                    command.script, [(start, end, replacement)])
    return None


def _offending_token(output):
    """Returns the token the error output names, or None."""
    for pattern in _TOKEN_PATTERNS:
        match = pattern.search(output)
        if match:
            return match.group(1)
    return None


def _suggestions(output):
    """Returns the distinct quote-stripped suggestion lines."""
    return set(stripped for stripped in
               (_unquoted(line) for line in
                get_all_matched_commands(output, _SEPARATORS))
               if stripped)


def _unquoted(token):
    if (len(token) > 1 and token[0] == token[-1]
            and token[0] in ('"', "'")):
        return token[1:-1]
    return token
