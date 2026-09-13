import os
import subprocess
import sys


def _run_with_stub_bashlex(tmpdir):
    """Runs a fresh interpreter with a broken bashlex shadowing the real one."""
    tmpdir.join('bashlex.py').write("raise ImportError('stub')\n")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    old_path = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = os.pathsep.join(
        [str(tmpdir), repo_root] + ([old_path] if old_path else []))
    code = ("import thefuck.entrypoints.fix_command; "
            "from thefuck.shell_ast import AST_AVAILABLE, bashlex; "
            "print(AST_AVAILABLE); print(bashlex)")
    return subprocess.check_output([sys.executable, '-c', code], env=env)


def test_guard_off_when_bashlex_unimportable(tmpdir):
    """With bashlex broken, the module still imports with the guard off."""
    assert _run_with_stub_bashlex(tmpdir).split() == [b'False', b'None']


def test_ast_available_reflects_bashlex():
    """The guard is on exactly when bashlex imports on python 3."""
    try:
        import bashlex  # noqa: F401
        bashlex_importable = True
    except ImportError:
        bashlex_importable = False

    from thefuck.shell_ast import AST_AVAILABLE

    assert AST_AVAILABLE == (bashlex_importable and sys.version_info[0] == 3)
