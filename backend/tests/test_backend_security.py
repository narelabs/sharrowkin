from __future__ import annotations

import pytest

from backend.core.tools import run_terminal_command, split_safe_command


def test_split_safe_command_blocks_wrapper_bypass():
    with pytest.raises(ValueError):
        split_safe_command('/usr/bin/env git status')


def test_split_safe_command_blocks_shell_operators():
    with pytest.raises(ValueError):
        split_safe_command('python -V | cat')


def test_run_terminal_command_executes_without_shell(tmp_path):
    result = run_terminal_command(tmp_path, 'python -c "print(123)"')
    assert result.success is True
    assert '123' in result.output


def test_run_terminal_command_reports_policy_error(tmp_path):
    result = run_terminal_command(tmp_path, 'rm -rf .')
    assert result.success is False
    assert result.exit_code == -2
    assert 'blocked' in result.output.lower()
