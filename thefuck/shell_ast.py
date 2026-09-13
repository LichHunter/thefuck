"""Structural analysis of shell commands, backed by bashlex.

Personal fork only: bashlex is GPL-3+ licensed while thefuck is MIT,
so this combination must not be distributed.
"""
import six

try:
    import bashlex
except ImportError:
    bashlex = None


AST_AVAILABLE = bashlex is not None and six.PY3

# bashlex 0.18 raises bare NotImplementedError for constructs it does
# not support (like `case` and arithmetic expansion) and AttributeError
# for empty or whitespace-only scripts; MatchedPairError, raised for
# unclosed quotes, subclasses ParsingError.
_FALLBACK_ERRORS = (AttributeError, NotImplementedError, TypeError)
if bashlex is not None:
    _FALLBACK_ERRORS += (bashlex.errors.ParsingError,)


class Segment(object):
    """One command of a pipeline with its words' char offsets.

    Every offset addresses the original script string, and every
    token is the raw span text (`script[start:end]`, quotes included
    as typed), so replacing a span with its token is always an
    identity and a corrected script is rebuilt by splicing
    replacements in at those offsets.
    """

    def __init__(self, words, start, end):
        self.words = words
        head, head_start, head_end = words[0]
        self.head = head
        self.head_start = head_start
        self.head_end = head_end
        self.start = start
        self.end = end


def parse(script):
    """Splits a script into pipeline command segments.

    Falls back to a single flat segment when bashlex is missing or
    cannot parse the script, so callers always get a usable view.
    """
    if not AST_AVAILABLE:
        return [_flat_segment(script)]
    try:
        trees = bashlex.parse(script)
    except _FALLBACK_ERRORS:
        return [_flat_segment(script)]
    collector = _SegmentCollector(script)
    for tree in trees:
        collector.visit(tree)
    if not collector.segments:
        return [_flat_segment(script)]
    return collector.segments


def splice(script, replacements):
    """Rebuilds a script from (start, end, new_text) replacements.

    Replacements are applied right-to-left so earlier offsets stay
    valid; overlapping spans raise ValueError because callers must
    never overlap.
    """
    ordered = sorted(replacements, key=lambda replacement: replacement[0])
    for index in range(1, len(ordered)):
        if ordered[index][0] < ordered[index - 1][1]:
            raise ValueError('overlapping replacements: {} and {}'.format(
                ordered[index - 1], ordered[index]))
    for start, end, text in reversed(ordered):
        script = script[:start] + text + script[end:]
    return script


def _flat_segment(script):
    """Builds the fallback segment from space-split words.

    Mirrors the flat view of `learned.get_correction`: offsets follow
    `script.split(' ')` exactly, so consecutive spaces yield empty
    tokens with zero-width spans at their true positions.
    """
    words = []
    start = 0
    for token in script.split(' '):
        end = start + len(token)
        words.append((token, start, end))
        start = end + 1
    return Segment(words, 0, len(script))


if AST_AVAILABLE:
    class _SegmentCollector(bashlex.ast.nodevisitor):
        """Collects command nodes as segments.

        Redirect and assignment parts are skipped, so their words
        never enter a segment; nested commands (inside substitutions
        or compounds of an already collected command) are skipped the
        same way by not descending into a command's parts.
        """

        def __init__(self, script):
            self.script = script
            self.segments = []

        def visitcommand(self, node, parts):
            words = [(self.script[part.pos[0]:part.pos[1]],
                      part.pos[0], part.pos[1])
                     for part in node.parts if part.kind == 'word']
            if words:
                self.segments.append(
                    Segment(words, node.pos[0], node.pos[1]))
            return False
