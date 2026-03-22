"""Command validation for the Az CLI Runner.

Validates and sanitizes incoming Azure CLI commands before execution.
Ensures that commands cannot modify authentication state or subscription context,
as these are managed by the service.
"""

import shlex
from typing import List


# Blocked command patterns - these subcommands are managed by the service
BLOCKED_SUBCOMMANDS: List[List[str]] = [
    ["login"],
    ["logout"],
    ["account", "set"],
    ["account", "list"],
    ["account", "show"],
    ["account", "clear"],
]


class CommandValidationError(Exception):
    """Raised when a command fails validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def parse_command(command: str) -> List[str]:
    """Parse a command string into an argument list.

    Uses shlex.split for safe shell-like parsing without actual shell execution.

    Args:
        command: The raw command string from the user.

    Returns:
        A list of argument strings.

    Raises:
        CommandValidationError: If the command string cannot be parsed.
    """
    try:
        args = shlex.split(command)
    except ValueError as e:
        raise CommandValidationError(f"Invalid command syntax: {e}")

    if not args:
        raise CommandValidationError("Empty command")

    return args


def validate_command(args: List[str]) -> List[str]:
    """Validate that a parsed command is allowed to run.

    Strips a leading 'az' token if present, then checks that the remaining
    subcommands are not in the blocked list.

    Args:
        args: The parsed argument list from parse_command().

    Returns:
        The validated argument list (with leading 'az' stripped if present).

    Raises:
        CommandValidationError: If the command is blocked or invalid.
    """
    if not args:
        raise CommandValidationError("Empty command")

    # Strip leading 'az' if present — users may or may not include it
    working_args = list(args)
    if working_args[0] == "az":
        working_args = working_args[1:]

    if not working_args:
        raise CommandValidationError("No command specified after 'az'")

    # Check against blocked subcommands
    for blocked in BLOCKED_SUBCOMMANDS:
        if len(working_args) >= len(blocked):
            if [a.lower() for a in working_args[: len(blocked)]] == blocked:
                raise CommandValidationError(
                    f"Command '{' '.join(blocked)}' is not allowed. "
                    "Authentication and subscription management are handled by the service."
                )

    return working_args
