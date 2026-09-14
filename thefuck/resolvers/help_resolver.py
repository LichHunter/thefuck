"""Generic subcommand typos fixed from the binary's own `--help`.

Trigger: a pipeline segment whose head resolves on $PATH but whose
first non-flag token is not a listed subcommand of that binary. Only
the first subcommand level is considered (`git remote addd` is out).

Caching choice: the docker rule wraps its loader in
`utils.cache(which('docker'))` at import time because its binary is
static; here the binary is only known at call time, so every resolved
binary path gets its own `cache(binary_path)`-wrapped loader stored in
the module-level `_command_loaders` dict. That reuses the mtime-keyed
`thefuck.utils.Cache` machinery (a changed binary re-runs `--help`)
and honors `cache.disabled` without calling `utils._cache` by hand.

Personal fork only: depends on bashlex (GPL-3+), do not distribute.
"""
import os
import subprocess

from thefuck import shell_ast, typo
from thefuck.utils import cache, which


_TIMEOUT = 2
_SECTION_HEADERS = ('Commands:', 'Management Commands:',
                    'Available Commands:')

_command_loaders = {}


def get_help_correction(script):
    """Returns the script with misspelled subcommands fixed, or None."""
    if not shell_ast.AST_AVAILABLE:
        return None
    replacements = []
    for segment in shell_ast.parse(script):
        replacement = _segment_replacement(segment)
        if replacement is not None:
            replacements.append(replacement)
    if not replacements:
        return None
    return shell_ast.splice(script, replacements)


def _segment_replacement(segment):
    """Returns a (start, end, token) fix for one segment, or None."""
    head = segment.head
    # sudo is out of scope (single-level fix); `=`/`/`/`.` heads are
    # flat-fallback artifacts like `VAR=value` or `./tool`, not names
    # this resolver should consult --help for.
    if head == 'sudo' or '=' in head or '/' in head or '.' in head:
        return None
    binary_path = which(head)
    if binary_path is None:
        return None
    for word in segment.words[1:]:
        token, _, _ = word
        if not token or token.startswith('-'):
            continue
        return _token_replacement(word, head, binary_path)
    return None


def _token_replacement(word, binary_name, binary_path):
    """Returns the (start, end, match) fix for one subcommand token."""
    commands = _get_commands(binary_path, binary_name)
    if not commands:
        return None
    token, start, end = word
    if token in commands:
        return None
    # Same gate shape as learned.guess_from_path: length-scaled
    # floor (see `typo.floor_ok`), exactly one distinct survivor.
    matches = set(command for command in commands
                  if typo.floor_ok(token, command))
    if len(matches) != 1:
        return None
    return start, end, matches.pop()


def _get_commands(binary_path, binary_name):
    loader = _command_loaders.get(binary_path)
    if loader is None:
        loader = cache(binary_path)(_load_commands)
        _command_loaders[binary_path] = loader
    return loader(binary_name)


def _load_commands(binary_name):
    """Spawns `<binary> --help`; returns its subcommands or None.

    The resolved binary path that keys the mtime cache is bound by the
    `cache(binary_path)` factory in `_get_commands`, not by an unused
    parameter here.
    """
    env = dict(os.environ, LC_ALL='C', LANG='C')
    try:
        proc = subprocess.Popen(
            [binary_name, '--help'], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
    except OSError:
        return None
    try:
        stdout, stderr = proc.communicate(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return None
    lines = stdout.decode('utf-8', 'replace').splitlines()
    if not lines:
        lines = stderr.decode('utf-8', 'replace').splitlines()
    return _parse_commands(lines)


def _parse_commands(lines):
    """First tokens of indented entries under command-section headers.

    A section ends at the first blank or non-indented line; help with
    no known header yields None so the caller declines.
    """
    commands = []
    found_section = False
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not line[:1].isspace() and stripped in _SECTION_HEADERS:
            found_section = True
            in_section = True
        elif not stripped:
            in_section = False
        elif in_section and line[:1].isspace():
            commands.append(stripped.split()[0])
        else:
            in_section = False
    return commands if found_section else None
