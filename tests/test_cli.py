"""Tests for the CLI module."""

from click.testing import CliRunner
from docker_volume_tools.cli import cli

def test_list_command():
    """Test the list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ['list'])
    assert result.exit_code == 0
    assert "Listing volumes..." in result.output

def test_inspect_command():
    """Test the inspect command."""
    runner = CliRunner()
    result = runner.invoke(cli, ['inspect', 'test-volume'])
    assert result.exit_code == 0
    assert "Inspecting volume test-volume" in result.output 