# Local OS Agent 🤖

A production-ready, modular OS-level Agentic Assistant that interfaces with locally hosted Large Language Models (via OpenAI-compatible endpoints like Ollama or LM Studio) to execute desktop automation tasks across audio, media, dynamic Steam gaming, system diagnostics, and window management with a multi-tool execution loop and a safety gatekeeper.

---

## Key Features

1. **Exact System Prompt & JSON Enforcement**:
   - Injects the strict system prompt directly into the agent.
   - Robust regex JSON extractor (`re.search(r"(\{[\s\S]*\})", text)`) isolates the JSON payload even when small local models (7B/8B/14B) prepend conversational fluff or markdown code blocks.

2. **Accurate Master Volume Control (`pycaw`)**:
   - Uses `SetMasterVolumeLevelScalar()` with a 0.0–1.0 linear float mapping directly to 0–100 percentages, avoiding logarithmic decibel math.
   - Master mute toggle via `GetMute()` / `SetMute()`.

3. **Dynamic Steam Discovery & Fuzzy Launcher**:
   - Automatically resolves the Steam installation directory from the Windows Registry (`HKCU\Software\Valve\Steam\SteamPath`).
   - Uses the dedicated `vdf` library to parse `libraryfolders.vdf` and all `appmanifest_*.acf` across multiple library drives.
   - Real-time catalog mapping game names to numeric `appid`s.
   - Fuzzy string matching (`difflib` + substring scoring) to launch games via `steam://rungameid/{app_id}`.

4. **Media & Application Controls**:
   - Direct YouTube queries and browser search links.
   - Global media virtual keys (`play_pause`, `next_track`, `prev_track`) using Windows virtual keycodes (`0xB3`, `0xB0`, `0xB1`).
   - Native application launcher with common aliases (`calculator`, `notepad`, `terminal`, etc.).

5. **Contextual Safety Gatekeeper**:
   - Sensitive actions (`kill_process`, `shutdown`, `sleep_pc`) require user confirmation `[y/N]`.
   - **Contextual Thought UI**: Displays the LLM's `thought` string right alongside the prompt so the user has full rationale before approving.

---

## Directory Structure

```
local-os-agent/
├── config.py             # App configuration, base URL, model name, paths
├── schemas.py            # Pydantic models (ToolAction, AgentResponse, etc.) & SYSTEM_PROMPT
├── agent.py              # OSAgent core, LLM client, regex JSON parser, multi-tool executor
├── main.py               # CLI runner, interactive REPL, diagnostic tool
├── requirements.txt      # Python dependencies
├── README.md             # Documentation and usage guide
│
├── tools/
│   ├── __init__.py       # Tool registry, decorators, dispatcher, safety gatekeeper
│   ├── audio.py          # set_volume, mute_toggle (pycaw scalar)
│   ├── media.py          # play_youtube, media_control (virtual keys)
│   ├── steam.py          # Dynamic Steam VDF scanner & fuzzy launcher
│   └── system.py         # launch_app, get_system_stats, take_screenshot, minimize_all_windows,
│                         # sensitive tools: kill_process, shutdown, sleep_pc
│
└── tests/
    ├── __init__.py
    ├── test_schemas.py   # Schema validation & JSON regex extraction tests
    ├── test_steam.py     # Steam VDF parsing & fuzzy game matching tests
    ├── test_tools.py     # Core tools & registry tests
    └── test_agent.py     # Multi-tool chaining & safety confirmation tests
```

---

## Quickstart

### 1. Installation
Install the required packages in Python 3.11+:
```bash
pip install -r requirements.txt
```

### 2. Verify Tool Diagnostics
Run the hardware and toolset diagnostic (tests Steam discovery, audio, screen capture, and system stats):
```bash
python main.py --test-tools
```

### 3. Run with Ollama
Make sure your local Ollama server is running (defaults to `http://localhost:11434/v1`):
```bash
# Interactive REPL
python main.py --model llama3.1:latest

# Single-shot prompt mode
python main.py --model llama3.1:latest --prompt "Turn volume to 30 and check my CPU"
```

### 4. Run with LM Studio / vLLM
```bash
python main.py --base-url http://localhost:1234/v1 --model local-model
```

---

## Running Unit Tests
```bash
python -m unittest discover tests
```

