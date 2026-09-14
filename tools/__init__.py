"""Tool registry and execution dispatcher for the Local OS Agent."""

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from schemas import ToolExecutionResult

logger = logging.getLogger("local_os_agent.tools")


@dataclass
class ToolDefinition:
    name: str
    func: Callable[..., Any]
    description: str
    sensitive: bool = False
    signature: inspect.Signature | None = None


_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(name: Any = None, description: str = "", sensitive: bool = False):
    """Decorator to register a tool function in the agent's toolset."""
    if callable(name):
        func = name
        tool_name = func.__name__
        tool_desc = description or (func.__doc__ or "").strip()
        sig = inspect.signature(func)
        _REGISTRY[tool_name] = ToolDefinition(
            name=tool_name,
            func=func,
            description=tool_desc,
            sensitive=sensitive,
            signature=sig,
        )
        return func

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()
        sig = inspect.signature(func)
        _REGISTRY[tool_name] = ToolDefinition(
            name=tool_name,
            func=func,
            description=tool_desc,
            sensitive=sensitive,
            signature=sig,
        )
        return func

    return decorator


def get_tool(name: str) -> ToolDefinition | None:
    """Retrieve a registered tool definition by name."""
    return _REGISTRY.get(name)


def list_tools() -> dict[str, ToolDefinition]:
    """Return all registered tools."""
    return dict(_REGISTRY)


def execute_tool(
    tool_name: str,
    args: dict[str, Any] | None = None,
    bypass_confirmation: bool = False,
) -> ToolExecutionResult:
    """
    Execute a registered tool by name with arguments.
    If the tool is marked sensitive and bypass_confirmation is False,
    returns status='awaiting_confirmation'.
    """
    args = args or {}
    tool_def = get_tool(tool_name)

    if not tool_def:
        return ToolExecutionResult(
            tool=tool_name,
            args=args,
            success=False,
            status="error",
            message=f"Tool '{tool_name}' is not recognized.",
        )

    # Contextual Safety Gatekeeper check
    if tool_def.sensitive and not bypass_confirmation:
        return ToolExecutionResult(
            tool=tool_name,
            args=args,
            success=False,
            status="awaiting_confirmation",
            message=f"Action '{tool_name}' requires explicit user confirmation.",
        )

    try:
        # Validate arguments against signature if available
        if tool_def.signature:
            bound_args = tool_def.signature.bind(**args)
            bound_args.apply_defaults()
            result = tool_def.func(*bound_args.args, **bound_args.kwargs)
        else:
            result = tool_def.func(**args)

        # Standardize return values
        if isinstance(result, ToolExecutionResult):
            return result
        elif isinstance(result, tuple) and len(result) == 2:
            success, output = result
            if isinstance(output, (dict, list)):
                return ToolExecutionResult(
                    tool=tool_name,
                    args=args,
                    success=bool(success),
                    status="success" if success else "error",
                    message="Data retrieved successfully." if success else "Error retrieving data.",
                    data=output,
                )
            else:
                return ToolExecutionResult(
                    tool=tool_name,
                    args=args,
                    success=bool(success),
                    status="success" if success else "error",
                    message=str(output),
                    data=output if not isinstance(output, str) else None,
                )
        else:
            return ToolExecutionResult(
                tool=tool_name,
                args=args,
                success=True,
                status="success",
                message=str(result) if result is not None else "Action completed successfully.",
                data=result,
            )
    except TypeError as te:
        logger.error(f"Argument mismatch for tool '{tool_name}': {te}")
        return ToolExecutionResult(
            tool=tool_name,
            args=args,
            success=False,
            status="error",
            message=f"Invalid arguments for '{tool_name}': {te}",
        )
    except Exception as e:
        logger.exception(f"Error executing tool '{tool_name}': {e}")
        return ToolExecutionResult(
            tool=tool_name,
            args=args,
            success=False,
            status="error",
            message=f"Execution error in '{tool_name}': {e}",
        )


# Import modules so their @register_tool decorators run
from tools import (
    ai_telemetry,  # noqa: F401, E402
    audio,  # noqa: F401, E402
    audio_ducking,  # noqa: F401, E402
    companion,  # noqa: F401, E402
    discord_relay,  # noqa: F401, E402
    flight,  # noqa: F401, E402
    game_clipper,  # noqa: F401, E402
    jellyfin,  # noqa: F401, E402
    media,  # noqa: F401, E402
    sfx,  # noqa: F401, E402
    songs,  # noqa: F401, E402
    soundboard,  # noqa: F401, E402
    steam,  # noqa: F401, E402
    subject_wellness,  # noqa: F401, E402
    system,  # noqa: F401, E402
    vision,  # noqa: F401, E402
    web,  # noqa: F401, E402
    zimaos,  # noqa: F401, E402
)
