from subprocess import Popen, PIPE
import io
import os
import six
import sys
from .. import logs
from ..conf import settings
from ..utils import DEVNULL
from .generic import Generic


class Nushell(Generic):
    friendly_name = 'Nushell Shell'

    def get_aliases(self):
        aliases = {}
        command = 'help aliases | select name expansion | each { |row| $row.name + " ; " + $row.expansion } | str join (char nl)'
        proc = Popen(['nu', '-l', '-c', command], stdout=PIPE, stderr=DEVNULL)
        if proc.stdout is None:
            return aliases
        alias_out = proc.stdout.read().decode('utf-8').strip()
        for alias in alias_out.split('\n'):
            split_alias = alias.split(" ; ")
            if len(split_alias) == 2:
                name, value = split_alias
                aliases[name] = value
        return aliases

    def app_alias(self, alias_name):
        return 'alias {0} = thefuck $"(history | last 1 | get command | get 0)"'.format(alias_name)

    def _get_history_file_name(self):
        return os.path.expanduser('~/.config/nushell/history.txt')

    def _get_history_line(self, command_script):
        return u'{}\n'.format(command_script)

    def _get_history_lines(self):
        """Returns list of history entries."""
        history_file_name = self._get_history_file_name()
        if os.path.isfile(history_file_name):
            with io.open(history_file_name, 'r',
                         encoding='utf-8', errors='ignore') as history_file:

                lines = history_file.readlines()
                if settings.history_limit:
                    lines = lines[-settings.history_limit:]

                for line in self._join_continuations(lines):
                    prepared = self._script_from_history(line) \
                        .strip()
                    if prepared:
                        yield prepared

    def _join_continuations(self, lines):
        """Joins lines ending with a backslash with the next line.

        Nushell escapes multiline commands in its plaintext history
        with a backslash at the end of each continued line.

        """
        joined = []
        pending = u''
        for line in lines:
            stripped = line.rstrip()
            if stripped.endswith('\\'):
                pending += stripped[:-1].rstrip() + u' '
            else:
                joined.append(pending + line)
                pending = u''
        if pending:
            joined.append(pending)
        return joined

    def and_(self, *commands):
        return u' and '.join(commands)

    def or_(self, *commands):
        return u' or '.join(commands)

    def how_to_configure(self):
        return self._create_shell_configuration(
            content='alias fuck = thefuck $"(history | last 1 | get command | get 0)"',
            path="$nu.config-path",
            reload="source $nu.config-path"
        )

    def _script_from_history(self, line):
        return line

    def put_to_history(self, command):
        """Adds fixed command to shell history."""
        try:
            history_file_name = self._get_history_file_name()
            if os.path.isfile(history_file_name):
                with open(history_file_name, 'a') as history:
                    entry = self._get_history_line(command)
                    if six.PY2:
                        history.write(entry.encode('utf-8'))
                    else:
                        history.write(entry)
        except IOError:
            logs.exception("Can't update history", sys.exc_info())

    def _get_version(self):
        """Returns the version of the current shell"""
        proc = Popen(['nu', '--version'], stdout=PIPE, stderr=DEVNULL)
        if proc.stdout:
            return proc.stdout.read().decode('utf-8')
        else:
            raise Exception("Could not get the version of the current shell")
