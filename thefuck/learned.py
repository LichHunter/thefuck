import atexit
import os
import shelve
import time
from difflib import get_close_matches

from . import logs, shell_ast
from .utils import get_all_executables, which

try:
    import dbm

    _shelve_open_error = (dbm.error,)
except ImportError:
    try:
        import anydbm

        _shelve_open_error = (anydbm.error,)
    except ImportError:
        _shelve_open_error = ()


GUESS_CUTOFF = 0.8


class LearnedCorrections(object):
    def __init__(self):
        self._db = None

    def _init_db(self):
        try:
            self._setup_db()
        except Exception:
            logs.debug("Unable to init learned-corrections db")
            self._db = {}

    def _setup_db(self):
        cache_dir = self._get_cache_dir()
        cache_path = os.path.join(cache_dir, "thefuck_learned")
        try:
            self._db = shelve.open(cache_path)
        except _shelve_open_error + (ImportError,):
            logs.warn("Removing possibly out-dated learned-corrections db")
            for suffix in ("", ".db", ".dir", ".bak", ".dat"):
                path = cache_path + suffix
                if os.path.exists(path):
                    os.remove(path)
            self._db = shelve.open(cache_path)
        atexit.register(self._db.close)

    @staticmethod
    def _get_cache_dir():
        cache_dir = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        try:
            os.makedirs(cache_dir)
        except OSError:
            if not os.path.isdir(cache_dir):
                raise
        return cache_dir

    @property
    def db(self):
        if self._db is None:
            self._init_db()
        return self._db

    def record(self, original_script, corrected_script):
        if original_script == corrected_script:
            return

        db = self.db
        now = time.time()

        original_parts = original_script.split()
        corrected_parts = corrected_script.split()

        full_key = "cmd:" + original_script
        entry = db.get(full_key, {})
        entry["corrected"] = corrected_script
        entry["count"] = entry.get("count", 0) + 1
        entry["timestamp"] = now
        db[full_key] = entry

        # Word-level diffs: only when token counts match, store each
        # changed token keyed by position so lookups can generalise
        # (e.g. learning "git psuh origin main" also fixes "git psuh origin dev")
        if (
            original_parts
            and corrected_parts
            and len(original_parts) == len(corrected_parts)
        ):
            for i, (orig_tok, corr_tok) in enumerate(
                zip(original_parts, corrected_parts)
            ):
                if orig_tok == corr_tok:
                    continue
                if i == 0:
                    key = "word:" + orig_tok
                else:
                    # Keyed under the corrected cmd name so "gti psuh"
                    # resolves via word:gti→git then part:git:psuh→push
                    key = "part:" + corrected_parts[0] + ":" + orig_tok
                part_entry = db.get(key, {})
                part_entry["replacement"] = corr_tok
                part_entry["count"] = part_entry.get("count", 0) + 1
                part_entry["timestamp"] = now
                db[key] = part_entry

        self._sync()

    def get_correction(self, script):
        db = self.db

        full_key = "cmd:" + script
        entry = db.get(full_key)
        if entry:
            return entry["corrected"]

        parts = script.split()
        if not parts:
            return None

        corrected_parts = list(parts)
        found = False

        word_entry = db.get("word:" + parts[0])
        if word_entry:
            corrected_parts[0] = word_entry["replacement"]
            found = True

        # Part lookups use the (possibly corrected) cmd name so that
        # "gti psuh" resolves even though parts are stored under "git"
        cmd_name = corrected_parts[0]
        for i in range(1, len(parts)):
            part_entry = db.get("part:" + cmd_name + ":" + parts[i])
            if part_entry:
                corrected_parts[i] = part_entry["replacement"]
                found = True

        if found:
            return " ".join(corrected_parts)

        return None

    def guess_from_path(self, script):
        """Guesses what the user meant by fuzzy-matching a mistyped
        command token against executables from $PATH and shell aliases,
        for the head of every pipeline segment, so a typo after a pipe
        is fixed as reliably as a leading one.

        Returns the corrected script only when at least one segment
        has exactly one unambiguous close match, so asking the user
        stays the last resort.
        """
        replacements = []
        for segment in shell_ast.parse(script):
            words = segment.words
            index = 1 if words[0][0] == 'sudo' and len(words) > 1 else 0
            token, start, end = words[index]
            # Raw spans keep their quotes; the gates must see the typed
            # word while the whole quoted span is replaced below.
            if (len(token) > 1 and token[0] == token[-1]
                    and token[0] in ('"', "'")):
                token = token[1:-1]
            if not token or '/' in token or '.' in token or which(token):
                continue
            candidates = [cmd for cmd in get_close_matches(
                token, get_all_executables(), n=5, cutoff=GUESS_CUTOFF)
                if cmd.startswith(token[0])]
            if len(candidates) != 1:
                continue
            replacements.append((start, end, candidates[0]))
        if not replacements:
            return None
        return shell_ast.splice(script, replacements)

    def clear(self):
        db = self.db
        for key in list(db.keys()):
            del db[key]
        self._sync()

    def _sync(self):
        try:
            self.db.sync()
        except AttributeError:
            pass


_learned = LearnedCorrections()

record = _learned.record
get_correction = _learned.get_correction
guess_from_path = _learned.guess_from_path
clear = _learned.clear
