# Developer & AI Agent Guidelines for local-os-agent (GLaDOS)

This document provides mandatory architecture standards, code style rules, and developer workflow commands for both human contributors and AI pair programming assistants working on this repository.

---

## 1. Quick Development Commands (`uv` Workflow)

All dependency management and execution must be performed using `uv`:

```bash
# Install or synchronize all runtime and dev dependencies
uv sync --all-extras

# Run the complete test suite via pytest
uv run pytest

# Run fast unit tests only (< 2 seconds)
uv run pytest -m "unit"

# Run cross-platform and headless degradation verification
uv run pytest -m "cross_platform or headless"

# Run linter and inspect code quality
uv run ruff check .

# Automatically fix lint issues and sort imports
uv run ruff check --fix .

# Format the codebase with Ruff
uv run ruff format .

# Launch GLaDOS CLI
uv run glados

# Launch GLaDOS Amber CRT Web Management Console
uv run glados-web
```

---

## 2. Architecture & Code Structure Rules

### Hexagonal Architecture (Ports & Adapters)
- **Domain & Ports (`app/ports/`)**: Pure Python interfaces using `typing.Protocol` or `abc.ABC`. Must have zero hardware or operating-system dependencies.
- **Platform Isolation (`app/adapters/`)**:
  - **Windows Adapters (`app/adapters/windows/`)**: All Win32 APIs, COM interfaces (`pycaw`, `comtypes`), and `ctypes.windll` calls must be strictly confined to this folder.
  - **Linux Adapters (`app/adapters/linux/`)**: PipeWire/PulseAudio (`wpctl`, `pactl`), `playerctl`, and systemd integrations.
  - **Zero Top-Level OS Imports**: Never place `import winreg`, `ctypes.windll`, or `import pycaw` at module level outside of `app/adapters/windows/`. Modules must import cleanly on any operating system.
- **Inversion of Control (`injector`)**:
  - Use `injector.inject` for constructors.
  - Modules register their dependencies in `app/core/modules.py`.
  - The IoC container automatically binds the appropriate platform adapter based on `sys.platform`.

### Dual-Channel Logging Standards
- **Zero Raw `print()` Statements**: Do not use `print()` in business logic, adapters, or service layers.
- **UI Stdout Logger (`app.core.logging.ui_logger`)**: Used exclusively for user-facing terminal prompts, Aperture ASCII HUDs, and GLaDOS conversational responses.
- **Debug File Logger (`app.core.logging.debug_logger`)**: Captures detailed `DEBUG`, `INFO`, `WARNING`, and `ERROR` logs with timestamps and tracebacks to `logs/glados_debug.log`.

### LangChain Tool-Calling Standards
- All tools must be registered via `@tool` with strict **Pydantic parameter schemas** (`BaseModel`, `Field(description=...)`).
- Never introduce rigid, hardcoded regular expression overrides in the agent loop. Let the LLM handle intent parsing dynamically.
- Always provide an isolated fallback resolver (`app/agent/fallback.py`) for critical survival commands (`hw`, `server`, `flight`, `cls`) when the LLM is offline.

---

## 3. Strict Coding & Documentation Rules

1. **Zero-Emoji Rule**:
   - The UI and terminal screens must have strictly zero emojis across all unicode ranges.
   - Code comments and docstrings must also be completely free of emojis.
   - Use clean ASCII art, brackets (`[MIC: OFF]`, `[* LIVE]`), and alphanumeric symbols (`+`, `-`, `=`, `|`, `*`).
2. **Comment Quality**:
   - Every class, port, adapter, and public method must include concise, human-readable docstrings explaining purpose, inputs, and expected outcomes.
   - Complex logic must have explanatory inline comments detailing rationale.
3. **Headless & Container Compatibility**:
   - Never assume physical sound cards, active window titles, or graphical display servers (`$DISPLAY`) are present.
   - Always implement graceful degradation paths (`NullAudioAdapter`, `NullVisionAdapter`) so the codebase can boot and run headless without unhandled exceptions.

