"""
Tests for the CLI layer (cli/commands.py).

These tests cover behavior that is verifiable without a browser: help output,
platform resolution errors, and the status command. Selenium-dependent stages
(fetch, sync, download, run) are not tested here.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli.commands import app
from scripts.platform import PlatformConfig

runner = CliRunner()


def _make_platform_config(
    name: str = "myplatform",
    display_name: str = "My Platform",
    login_url: str = "https://example.com/login",
    base: Path = Path("/tmp/nonexistent"),
) -> PlatformConfig:
    """Returns a minimal PlatformConfig for use in tests."""
    return PlatformConfig(
        name=name,
        display_name=display_name,
        login_url=login_url,
        course_links_path=base / "course_links.json",
        tree_dir=base / "trees",
        course_dir=base / "course",
    )


class TestCliHelp:
    """The top-level --help flag should succeed and list all commands."""

    def test_help_exits_zero(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_help_lists_run_command(self):
        result = runner.invoke(app, ["--help"])
        assert "run" in result.output

    def test_help_lists_status_command(self):
        result = runner.invoke(app, ["--help"])
        assert "status" in result.output

    def test_help_lists_fetch_command(self):
        result = runner.invoke(app, ["--help"])
        assert "fetch" in result.output

    def test_help_lists_sync_command(self):
        result = runner.invoke(app, ["--help"])
        assert "sync" in result.output

    def test_help_lists_download_command(self):
        result = runner.invoke(app, ["--help"])
        assert "download" in result.output

    def test_all_five_commands_present(self):
        result = runner.invoke(app, ["--help"])
        for cmd in ("run", "status", "fetch", "sync", "download"):
            assert cmd in result.output, f"Command '{cmd}' not found in help output"


class TestCliPlatformErrors:
    """Commands that require a platform should fail gracefully when none is available."""

    def test_no_platforms_configured_exits_1(self):
        with patch("cli.commands.list_platforms", return_value=[]):
            result = runner.invoke(app, ["run", "--platform", "anything", "--yes"])
        assert result.exit_code == 1

    def test_invalid_platform_name_exits_1(self):
        with patch("cli.commands.list_platforms", return_value=["real_platform"]):
            result = runner.invoke(app, ["run", "--platform", "nonexistent", "--yes"])
        assert result.exit_code == 1

    def test_no_platforms_status_returns_zero(self):
        # status warns but does not raise — it returns 0 when no platforms found
        with patch("cli.commands.list_platforms", return_value=[]):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_invalid_platform_fetch_exits_1(self):
        with patch("cli.commands.list_platforms", return_value=["other"]):
            result = runner.invoke(app, ["fetch", "--platform", "missing"])
        assert result.exit_code == 1

    def test_invalid_platform_sync_exits_1(self):
        with patch("cli.commands.list_platforms", return_value=["other"]):
            result = runner.invoke(app, ["sync", "--platform", "missing"])
        assert result.exit_code == 1

    def test_invalid_platform_download_exits_1(self):
        with patch("cli.commands.list_platforms", return_value=["other"]):
            result = runner.invoke(app, ["download", "--platform", "missing", "--yes"])
        assert result.exit_code == 1


class TestCliStatus:
    """The status command should show platform info without opening a browser."""

    def test_valid_platform_shows_display_name(self):
        cfg = _make_platform_config(display_name="Campus Virtual")
        with patch("cli.commands.list_platforms", return_value=["myplatform"]), \
             patch("cli.commands.load_platform", return_value=cfg):
            result = runner.invoke(app, ["status", "--platform", "myplatform"])
        assert result.exit_code == 0
        assert "Campus Virtual" in result.output

    def test_platform_flag_restricts_to_one_platform(self):
        cfg_a = _make_platform_config(name="alpha", display_name="Alpha Uni")
        cfg_b = _make_platform_config(name="beta", display_name="Beta Uni")

        def _mock_load(name: str) -> PlatformConfig:
            return cfg_a if name == "alpha" else cfg_b

        with patch("cli.commands.list_platforms", return_value=["alpha", "beta"]), \
             patch("cli.commands.load_platform", side_effect=_mock_load):
            result = runner.invoke(app, ["status", "--platform", "alpha"])

        assert result.exit_code == 0
        assert "Alpha Uni" in result.output
        assert "Beta Uni" not in result.output

    def test_missing_log_dir_shows_none(self, tmp_path: Path):
        cfg = _make_platform_config(base=tmp_path / "nonexistent")
        with patch("cli.commands.list_platforms", return_value=["myplatform"]), \
             patch("cli.commands.load_platform", return_value=cfg), \
             patch("scripts.utils.LOG_DIR", tmp_path / "no_logs_here"):
            result = runner.invoke(app, ["status", "--platform", "myplatform"])
        assert result.exit_code == 0
        assert "none" in result.output

    def test_status_shows_platform_name_key(self):
        cfg = _make_platform_config(name="upso", display_name="UPSO Virtual")
        with patch("cli.commands.list_platforms", return_value=["upso"]), \
             patch("cli.commands.load_platform", return_value=cfg):
            result = runner.invoke(app, ["status", "--platform", "upso"])
        assert result.exit_code == 0
        assert "upso" in result.output

    def test_status_shows_login_url(self):
        cfg = _make_platform_config(login_url="https://virtual.upso.edu.ar/login")
        with patch("cli.commands.list_platforms", return_value=["myplatform"]), \
             patch("cli.commands.load_platform", return_value=cfg):
            result = runner.invoke(app, ["status", "--platform", "myplatform"])
        assert result.exit_code == 0
        assert "https://virtual.upso.edu.ar/login" in result.output

    def test_status_shows_zero_courses_when_no_file(self):
        cfg = _make_platform_config()
        with patch("cli.commands.list_platforms", return_value=["myplatform"]), \
             patch("cli.commands.load_platform", return_value=cfg):
            result = runner.invoke(app, ["status", "--platform", "myplatform"])
        assert result.exit_code == 0
        # course_links_path doesn't exist → count should show 0
        assert "0" in result.output

    def test_status_multiple_platforms_without_flag(self):
        cfg_a = _make_platform_config(name="alpha", display_name="Alpha Uni")
        cfg_b = _make_platform_config(name="beta", display_name="Beta Uni")

        def _mock_load(name: str) -> PlatformConfig:
            return cfg_a if name == "alpha" else cfg_b

        with patch("cli.commands.list_platforms", return_value=["alpha", "beta"]), \
             patch("cli.commands.load_platform", side_effect=_mock_load):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Alpha Uni" in result.output
        assert "Beta Uni" in result.output
