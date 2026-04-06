from subprocess import Popen, PIPE
import os
import six
import sys
from .. import logs
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
        return command_script

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
