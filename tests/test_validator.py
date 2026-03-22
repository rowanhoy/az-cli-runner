"""Tests for command validation logic."""

import pytest

from app.validator import CommandValidationError, parse_command, validate_command


class TestParseCommand:
    """Tests for parse_command()."""

    def test_simple_command(self):
        assert parse_command("az group list") == ["az", "group", "list"]

    def test_command_with_flags(self):
        result = parse_command("az vm show --resource-group myRg --name myVm")
        assert result == [
            "az",
            "vm",
            "show",
            "--resource-group",
            "myRg",
            "--name",
            "myVm",
        ]

    def test_command_with_quoted_args(self):
        result = parse_command('az tag create --name "my tag"')
        assert result == ["az", "tag", "create", "--name", "my tag"]

    def test_empty_command(self):
        with pytest.raises(CommandValidationError, match="Empty command"):
            parse_command("")

    def test_invalid_syntax(self):
        with pytest.raises(CommandValidationError, match="Invalid command syntax"):
            parse_command('az group list --query "unclosed')

    def test_whitespace_only(self):
        with pytest.raises(CommandValidationError, match="Empty command"):
            parse_command("   ")


class TestValidateCommand:
    """Tests for validate_command()."""

    def test_valid_command_with_az_prefix(self):
        result = validate_command(["az", "group", "list"])
        assert result == ["group", "list"]

    def test_valid_command_without_az_prefix(self):
        result = validate_command(["group", "list"])
        assert result == ["group", "list"]

    def test_blocked_login(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "login"])

    def test_blocked_login_without_az(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["login"])

    def test_blocked_logout(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "logout"])

    def test_blocked_account_set(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "account", "set", "--subscription", "abc"])

    def test_blocked_account_list(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "account", "list"])

    def test_blocked_account_show(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "account", "show"])

    def test_blocked_account_clear(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "account", "clear"])

    def test_blocked_case_insensitive(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "LOGIN"])

    def test_blocked_login_with_extra_args(self):
        with pytest.raises(CommandValidationError, match="not allowed"):
            validate_command(["az", "login", "--service-principal"])

    def test_empty_args(self):
        with pytest.raises(CommandValidationError, match="Empty command"):
            validate_command([])

    def test_only_az(self):
        with pytest.raises(CommandValidationError, match="No command specified"):
            validate_command(["az"])

    def test_allowed_account_subcommand(self):
        # 'az account list-locations' should be allowed
        result = validate_command(["az", "account", "list-locations"])
        assert result == ["account", "list-locations"]

    def test_allowed_resource_command(self):
        result = validate_command(["az", "resource", "list"])
        assert result == ["resource", "list"]
