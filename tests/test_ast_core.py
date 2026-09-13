import pytest

from thefuck import shell_ast
from thefuck.shell_ast import parse, splice


needs_bashlex = pytest.mark.skipif(
    not shell_ast.AST_AVAILABLE, reason='bashlex is not available')


CORPUS = [
    'gti psuh | greo -i foo',
    'ls',
    'one | two | three',
    'a && b',
    'a; b',
    "echo 'hello world' foo",
    'echo "double quoted arg"',
    'cmd > file 2>&1',
    'FOO=bar cmd arg',
    'sudo apt-get install vim',
    'trailing spaces   ',
    'ls | where size > 1mb',
    'echo naïve',
    'cmd  arg',
    'cd /tmp && ls -la',
    'grep -lir . test | sort | uniq',
    'python -c "print(1)"',
    'echo a"b c"d',
    'sudo docker ps -a | grep exited',
    'echo one  >   file',
]

# Each entry falls back because bashlex 0.18 raises for it:
# `case` and $((...)) hit NotImplementedError, empty and whitespace-only
# scripts hit its empty-string AttributeError, the lone pipe is a
# ParsingError, and the unclosed quote raises MatchedPairError,
# which subclasses bashlex.errors.ParsingError.
FALLBACK_SCRIPTS = [
    'case $x in a) foo;; esac',
    'echo $((1+1))',
    '',
    '   ',
    '|',
    "'abc",
]

EXPECTED_HEADS = [
    ('gti psuh | greo -i foo', ['gti', 'greo']),
    ('ls', ['ls']),
    ('one | two | three', ['one', 'two', 'three']),
    ('a && b', ['a', 'b']),
    ('a; b', ['a', 'b']),
    ('trailing spaces   ', ['trailing']),
    ('ls | where size > 1mb', ['ls', 'where']),
    ('cd /tmp && ls -la', ['cd', 'ls']),
    ('grep -lir . test | sort | uniq', ['grep', 'sort', 'uniq']),
    ('sudo docker ps -a | grep exited', ['sudo', 'grep']),
    ('echo one  >   file', ['echo']),
]


@pytest.mark.parametrize('script', CORPUS)
def test_splice_with_no_replacements_is_identity(script):
    assert splice(script, []) == script


@needs_bashlex
@pytest.mark.parametrize('script', CORPUS)
def test_word_offsets_round_trip_byte_for_byte(script):
    segments = parse(script)
    for segment in segments:
        for token, start, end in segment.words:
            assert script[start:end] == token
            assert splice(script, [(start, end, token)]) == script
    everything = [(start, end, token)
                  for segment in segments
                  for token, start, end in segment.words]
    assert splice(script, everything) == script


@needs_bashlex
def test_replaces_misspelled_heads_across_pipeline():
    script = 'gti psuh | greo -i foo'
    replacements = []
    for segment in parse(script):
        if segment.head == 'gti':
            replacements.append(
                (segment.head_start, segment.head_end, 'git'))
        elif segment.head == 'greo':
            replacements.append(
                (segment.head_start, segment.head_end, 'grep'))
    assert splice(script, replacements) == 'git psuh | grep -i foo'


@needs_bashlex
@pytest.mark.parametrize('script,heads', EXPECTED_HEADS)
def test_segment_heads(script, heads):
    assert [segment.head for segment in parse(script)] == heads


@needs_bashlex
def test_pipeline_segments_carry_word_and_span_offsets():
    first, second = parse('gti psuh | greo -i foo')
    assert first.words == [('gti', 0, 3), ('psuh', 4, 8)]
    assert (first.head_start, first.head_end) == (0, 3)
    assert (first.start, first.end) == (0, 8)
    assert second.words == [('greo', 11, 15), ('-i', 16, 18),
                            ('foo', 19, 22)]
    assert (second.start, second.end) == (11, 22)


@needs_bashlex
def test_env_prefix_head_is_the_real_command():
    # bashlex 0.18 classifies `FOO=bar` as an assignment node, not a
    # word, so the first collected word is the command itself and the
    # head resolves to `cmd`.
    segment, = parse('FOO=bar cmd arg')
    assert segment.head == 'cmd'
    assert segment.words == [('cmd', 8, 11), ('arg', 12, 15)]


@needs_bashlex
def test_redirect_words_are_excluded_from_segments():
    segment, = parse('cmd > file 2>&1')
    assert segment.words == [('cmd', 0, 3)]


@needs_bashlex
def test_nushell_comparison_stays_byte_true():
    # `> 1mb` misparses as a redirect node; it must stay out of the
    # words while the remaining offsets keep addressing the original.
    first, second = parse('ls | where size > 1mb')
    assert first.words == [('ls', 0, 2)]
    assert second.words == [('where', 5, 10), ('size', 11, 15)]


@needs_bashlex
def test_quoted_word_spans_include_the_quotes():
    segment, = parse("echo 'hello world' foo")
    assert segment.words == [('echo', 0, 4), ("'hello world'", 5, 18),
                             ('foo', 19, 22)]
    assert splice("echo 'hello world' foo",
                  [(5, 18, "'hi'")]) == "echo 'hi' foo"


@needs_bashlex
def test_mixed_quoted_word_splices_as_one_span():
    segment, = parse('echo a"b c"d')
    assert segment.words == [('echo', 0, 4), ('a"b c"d', 5, 12)]
    assert splice('echo a"b c"d', [(5, 12, "'x y'")]) == "echo 'x y'"


@needs_bashlex
@pytest.mark.parametrize('script', FALLBACK_SCRIPTS)
def test_unparseable_scripts_fall_back_flat(script):
    segments = parse(script)
    assert len(segments) == 1
    segment = segments[0]
    assert [word[0] for word in segment.words] == script.split(' ')
    for token, start, end in segment.words:
        assert script[start:end] == token
    assert (segment.start, segment.end) == (0, len(script))


def test_flat_fallback_when_ast_disabled(monkeypatch):
    monkeypatch.setattr(shell_ast, 'AST_AVAILABLE', False)
    script = 'gti psuh | greo -i foo'
    segment, = parse(script)
    assert segment.head == 'gti'
    assert [word[0] for word in segment.words] == script.split(' ')
    for token, start, end in segment.words:
        assert script[start:end] == token
    assert (segment.start, segment.end) == (0, len(script))


def test_flat_fallback_offsets_survive_consecutive_spaces(monkeypatch):
    monkeypatch.setattr(shell_ast, 'AST_AVAILABLE', False)
    script = 'gti  psuh'
    segment, = parse(script)
    # 'gti  psuh'.split(' ') keeps an empty token between the spaces
    assert segment.words == [('gti', 0, 3), ('', 4, 4), ('psuh', 5, 9)]
    assert splice(script, [(0, 3, 'git')]) == 'git  psuh'


def test_splice_sorts_replacements_and_applies_right_to_left():
    assert splice('abcdef', [(4, 6, 'Y'), (0, 3, 'X')]) == 'XdY'


def test_splice_allows_touching_replacements():
    assert splice('abcdef', [(0, 3, 'X'), (3, 6, 'YZ')]) == 'XYZ'


def test_splice_rejects_overlapping_replacements():
    with pytest.raises(ValueError):
        splice('abcdef', [(0, 3, 'X'), (2, 5, 'Y')])
    with pytest.raises(ValueError):
        splice('abcdef', [(0, 3, 'X'), (0, 3, 'Y')])
