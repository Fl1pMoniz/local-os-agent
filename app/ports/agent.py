"""Conversational agent and intent execution port definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntentAgentPort(Protocol):
    """Protocol for the core agent that processes user input and executes actions."""

    def run(self, prompt: str) -> str:
        """Processes a natural language prompt and returns the agent's textual response."""
        ...

    def execute_command(self, command: str) -> tuple[bool, str]:
        """Directly parses and executes a command or tool call."""
        ...
