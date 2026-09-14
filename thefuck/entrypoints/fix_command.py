from pprint import pformat
import os
import sys
from difflib import SequenceMatcher
from .. import compose, const, danger, learned, logs, types
from ..conf import settings
from ..corrector import get_corrected_commands
from ..exceptions import EmptyCommand
from ..shells import Nushell, shell
from ..ui import select_command
from ..utils import get_alias, get_all_executables


def _get_raw_command(known_args):
    if known_args.force_command:
        return [known_args.force_command]
    elif not os.environ.get("TF_HISTORY"):
        return known_args.command
    else:
        history = os.environ["TF_HISTORY"].split("\n")[::-1]
        alias = get_alias()
        executables = get_all_executables()
        for command in history:
            diff = SequenceMatcher(a=alias, b=command).ratio()
            if diff < const.DIFF_WITH_ALIAS or command in executables:
                return [command]
    return []


def _run_learned(command, corrected, steps):
    """Runs an auto-applied correction, learning from the outcome.

    Under `settings.repeat` or a non-nushell parent shell the outcome
    cannot be observed (the script goes to the parent shell or a
    child `thefuck --repeat` process), so today's behavior stands:
    record immediately before the run, unless the composition only
    replayed a learned-db exact hit. Under nushell the db is closed
    before the run (so the child can safely open its own) and the
    fix is remembered only when the command succeeds — a failing
    fix is forgotten again.
    """
    replayed_learned_only = (len(steps) == 1
                             and steps[0][0] == compose.LEARNED_SOURCE)
    if settings.repeat or not isinstance(shell, Nushell):
        if not replayed_learned_only:
            learned.record(command.script, corrected.script)
        corrected.run(command)
        return
    learned.close_db()
    corrected.run(command)
    if corrected.returncode == 0:
        learned.record(command.script, corrected.script)
    else:
        learned.forget(command.script, corrected.script)


def fix_command(known_args):
    """Fixes previous command. Used when `thefuck` called without arguments."""
    settings.init(known_args)
    with logs.debug_time("Total"):
        logs.debug("Run with settings: {}".format(pformat(settings)))
        raw_command = _get_raw_command(known_args)

        try:
            command = types.Command.from_raw_script(raw_command)
        except EmptyCommand:
            logs.debug("Empty command, nothing to do")
            return

        learned_script, steps = compose.resolve(command)
        if learned_script is not None \
                and danger.is_dangerous(learned_script):
            # Belt and suspenders: the composer already declines
            # dangerous candidates; this guards against regressions.
            logs.debug("Refusing to auto-run dangerous correction, "
                       "asking instead: {}".format(learned_script))
            learned_script = None
        if learned_script is not None:
            for source, step in steps:
                logs.debug("Composed via {}: {}".format(source, step))
            learned_cmd = types.CorrectedCommand(
                script=learned_script, side_effect=None, priority=0
            )
            logs.show_corrected_command(learned_cmd)
            _run_learned(command, learned_cmd, steps)
            return

        corrected_commands = get_corrected_commands(command)
        selected_command = select_command(corrected_commands)

        if selected_command:
            learned.record(command.script, selected_command.script)
            selected_command.run(command)
        else:
            sys.exit(1)
