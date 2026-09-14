"""Conservative destructive-command detection for the auto-run gate.

`is_dangerous(script)` answers True whenever a script must not run
without confirmation. Parsing goes through bashlex directly: when
bashlex is unavailable or refuses the script the answer is True
(fail-safe), because the flat fallback is head-only and would miss
compound shapes such as `echo $((1+1)); rm -rf /`.

False positives (asking more often) are acceptable; false negatives
in the listed shapes are not.

Personal fork only: depends on bashlex (GPL-3+), do not distribute.
"""
import re

from . import shell_ast

_RECURSIVE_FLAG = re.compile(r'^-[a-zA-Z]*[rR]')
_OCTAL_MODE = re.compile(r'^[0-7]{3,4}$')
_PIPE_SHELLS = frozenset(('sh', 'bash', 'zsh', 'dash'))
_DESTRUCTIVE_HEADS = frozenset(('dd', 'shred', 'wipefs', 'mkswap'))


def is_dangerous(script):
    """Returns True when `script` must be confirmed, never auto-run."""
    if ':(){' in script or ': () {' in script:
        return True
    if not shell_ast.AST_AVAILABLE:
        return True
    try:
        trees = shell_ast.bashlex.parse(script)
    except shell_ast._FALLBACK_ERRORS:
        return True
    collector = _DangerCollector(script)
    for tree in trees:
        collector.visit(tree)
    for words, pipe_tail in collector.commands:
        if _words_dangerous(words, pipe_tail):
            return True
    return _redirects_dangerous(collector.redirect_targets)


def _words_dangerous(words, pipe_tail):
    """Matches one command's (sudo-stripped) words against the shapes."""
    while len(words) > 1 and words[0] == 'sudo':
        words = words[1:]
    if not words:
        return False
    head, args = words[0], words[1:]
    if head in ('rm', 'rmdir'):
        return any(_RECURSIVE_FLAG.match(arg) or arg == '--recursive'
                   for arg in args)
    if head in _DESTRUCTIVE_HEADS or head.startswith('mkfs'):
        return True
    if head == 'git' and args[:1] == ['push']:
        return any(arg in ('--force', '-f') for arg in args[1:])
    if head in ('chmod', 'chown'):
        return (any(_RECURSIVE_FLAG.match(arg) for arg in args)
                and any(_OCTAL_MODE.match(arg)
                        and set(arg[-3:]) <= set('67') for arg in args))
    if head == 'kill':
        return any(arg.startswith('-9') for arg in args)
    return pipe_tail and head in _PIPE_SHELLS


def _redirects_dangerous(targets):
    """Any redirect aimed at a file outside /tmp and /dev/null."""
    for target in targets:
        if target == '/dev/null':
            continue
        if target == '/tmp' or target.startswith('/tmp/'):
            continue
        return True
    return False


def _unquote(word):
    if len(word) > 1 and word[0] == word[-1] and word[0] in ('"', "'"):
        return word[1:-1]
    return word


def _redirect_target(part):
    """Returns a redirect's quote-stripped file target, or None.

    Heredocs are not file overwrites, and fd duplications like
    `2>&1` differ structurally: bashlex hands them a plain string
    where file targets are word nodes.
    """
    if part.type.startswith('<<'):
        return None
    output = part.output
    if not isinstance(output, _NODE_CLASS):
        return None
    return _unquote(output.word)


if shell_ast.AST_AVAILABLE:
    _NODE_CLASS = shell_ast.bashlex.ast.node

    class _DangerCollector(shell_ast.bashlex.ast.nodevisitor):
        """Collects command words and redirect targets from a tree.

        Unlike `shell_ast._SegmentCollector` (which skips redirect
        parts by design) this visitor keeps their targets, and by
        descending into command parts it also sees nested commands
        inside substitutions such as `echo $(rm -rf /)`.
        """

        def __init__(self, script):
            self.script = script
            self.commands = []
            self.redirect_targets = []
            self._pipe_tail_ids = set()

        def visitpipeline(self, node, parts):
            commands = [part for part in parts
                        if part.kind == 'command']
            self._pipe_tail_ids.update(
                id(part) for part in commands[1:])
            return True

        def visitcommand(self, node, parts):
            words = []
            for part in parts:
                if part.kind == 'word':
                    words.append(_unquote(
                        self.script[part.pos[0]:part.pos[1]]))
                elif part.kind == 'redirect':
                    target = _redirect_target(part)
                    if target is not None:
                        self.redirect_targets.append(target)
            self.commands.append(
                (words, id(node) in self._pipe_tail_ids))
            return True
