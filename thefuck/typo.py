"""Single-edit (Damerau distance 1) typo predicate.

`difflib.SequenceMatcher` rates adjacent transpositions (gti -> git)
well below similarity cutoffs that accept substitutions, so gates
that only use the ratio decline the most common keyboard slips.
Callers accept `single_edit(a, b)` matches as an additional path.
"""


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
