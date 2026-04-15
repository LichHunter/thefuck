import atexit
import os
import shelve
import time

from . import logs

try:
    import dbm

    _shelve_open_error = (dbm.error,)
except ImportError:
    try:
        import anydbm

        _shelve_open_error = (anydbm.error,)
    except ImportError:
        _shelve_open_error = ()


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
clear = _learned.clear
