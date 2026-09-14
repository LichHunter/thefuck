"""Single-edit (Damerau distance 1) typo predicate and
length-scaled similarity floors.

`difflib.SequenceMatcher` rates adjacent transpositions (gti -> git)
well below similarity cutoffs that accept substitutions, so gates
that only use the ratio decline the most common keyboard slips.
Callers accept `single_edit(a, b)` matches as an additional path.
"""
from difflib import SequenceMatcher


def floor_ok(a, b):
    """Returns True when `b` is a close-enough correction of `a`.

    The required ratio rises with word length,
    `max(0.6, 1 - 3.0 / max(len(a), len(b), 3))` (the minimum of 3
    only guards the division for the shortest words): zsh's spdist
    admits len/4 + 1 errors and nushell's did_you_mean a third of
    the length, while a fixed cutoff over-admits long words and a
    bare single-edit cap under-admits them. Single edits always
    pass, and the first character must match so a correction stays
    a typo fix of the same word, not a jump to a different one.
    """
    if a[:1] != b[:1]:
        return False
    if single_edit(a, b):
        return True
    floor = max(0.6, 1 - 3.0 / max(len(a), len(b), 3))
    return SequenceMatcher(None, a, b).ratio() >= floor


def single_edit(a, b):
    """Returns True when `a` and `b` differ by exactly one edit.

    One edit is a substitution, insertion, deletion or adjacent
    transposition (restricted Damerau distance of 1); equal strings
    are zero edits and return False.
    """
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return _equal_length_single_edit(a, b)
    if len(a) > len(b):
        return _contains_single_insertion(a, b)
    return _contains_single_insertion(b, a)


def _equal_length_single_edit(a, b):
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diffs) == 1:
        return True
    return (len(diffs) == 2 and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]])


def _contains_single_insertion(longer, shorter):
    for i in range(len(shorter)):
        if shorter[i] != longer[i]:
            return shorter[i:] == longer[i + 1:]
    return True
