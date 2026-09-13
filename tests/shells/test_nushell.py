# -*- coding: utf-8 -*-

import io
import pytest
from thefuck.shells import Nushell


@pytest.mark.usefixtures('no_memoize')
class TestNushell(object):
    @pytest.fixture
    def shell(self, mocker, tmp_path):
        shell = Nushell()
        mocker.patch.object(shell, '_get_history_file_name',
                            return_value=str(tmp_path / 'history.txt'))
        return shell

    @pytest.fixture
    def history_file(self, shell):
        def write(content):
            with io.open(shell._get_history_file_name(), 'w',
                         encoding='utf-8') as history:
                history.write(content)
        return write

    def test_put_to_history_writes_trailing_newline(self, shell,
                                                    history_file):
        history_file(u'')
        shell.put_to_history('cmd1')
        shell.put_to_history('cmd2')
        with io.open(shell._get_history_file_name(), 'r',
                     encoding='utf-8') as history:
            assert history.read() == u'cmd1\ncmd2\n'

    def test_get_history_after_put_to_history(self, shell, history_file):
        history_file(u'')
        shell.put_to_history('cmd1')
        shell.put_to_history('cmd2')
        assert list(shell.get_history()) == ['cmd1', 'cmd2']

    def test_get_history_joins_backslash_continuations(self, shell,
                                                       history_file):
        history_file(u'foo \\\nbar\nls\n')
        assert list(shell.get_history()) == [u'foo bar', 'ls']

    def test_get_history_when_file_missing(self, shell):
        assert list(shell.get_history()) == []

    def test_get_history_respects_history_limit(self, shell, history_file,
                                                settings):
        settings.history_limit = 2
        history_file(u'a\nb\nc\n')
        assert list(shell.get_history()) == ['b', 'c']
