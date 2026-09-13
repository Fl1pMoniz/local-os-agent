# Aperture OS - GLaDOS 🤖🧪

A production-ready, modular OS-level Agentic Assistant that interfaces with locally hosted Large Language Models (via Ollama or LM Studio) to execute desktop automation tasks across media, gaming, system settings, and multitasking with the iconic personality and voice of **GLaDOS** (Genetic Lifeform and Disk Operating System) from Valve's *Portal*.

---

## Key Features

1. **GLaDOS Persona & Conversational Intelligence**:
   - **Aperture Science Persona**: Coldly polite, clinically calm, darkly witty, and subtly sarcastic.
   - **Conversational Memory**: Holds multi-turn dialogue when spoken to (banter, cake inquiries, testing protocols) while reliably executing desktop tasks when ordered.
   - **GLaDOS Voice Synthesis**: Tuned synthetic neural voice (`glados` preset) featuring Ellen McLain's signature clinical, deadpan cadence and pitch.
   - **Wake Word Recognition**: Responds exclusively when addressed as **`"GLaDOS"`** or **`"Hey GLaDOS"`**, ignoring background room chatter.

2. **Ultra-Low VRAM Footprint (< 2.5 GB VRAM)**:
   - Configured with the optimized **`glados:3b`** model (based on LLaMA 3.2 3B).
   - Constrained to a 2,048 token context window, capping total GPU memory consumption at **2.3 GB VRAM** (leaving ~10 GB free on an RTX 4070 for games and background tasks).
   - Instant response latency (~1.0s).

3. **Exact System Prompt & JSON Enforcement**:
   - Injects the strict system prompt directly into the agent.
   - Robust regex JSON extractor (`re.search(r"(\{[\s\S]*\})", text)`) with automatic syntax repair for trailing commas.

3. **Master & Per-Application Volume Control (`pycaw`)**:
   - Master volume with `SetMasterVolumeLevelScalar()` (linear 0.0–1.0 float mapping to 0–100%).
   - Independent per-app volume slider control (`set_app_volume`, `list_app_volumes`) for Discord, Spotify, Chrome, games, etc.

4. **Dynamic Steam Discovery & Fuzzy Launcher**:
   - Automatically resolves the Steam installation directory from the Windows Registry (`HKCU\Software\Valve\Steam\SteamPath`).
   - Uses the dedicated `vdf` library to parse `libraryfolders.vdf` and all `appmanifest_*.acf` across multiple library drives.
   - Real-time catalog mapping game names to numeric `appid`s.
   - Fuzzy string matching (`difflib` + substring scoring) to launch games via `steam://rungameid/{app_id}`.

5. **Media & Application Controls**:
   - Direct YouTube queries and browser search links.
   - Global media virtual keys (`play_pause`, `next_track`, `prev_track`) using Windows virtual keycodes (`0xB3`, `0xB0`, `0xB1`).
   - Native application launcher with common aliases (`calculator`, `notepad`, `terminal`, etc.).

6. **Contextual Safety Gatekeeper**:
   - Sensitive actions (`kill_process`, `shutdown`, `sleep_pc`) require user confirmation `[y/N]`.
   - **Contextual Thought UI & Spoken Warning**: Displays and speaks the LLM's `thought` string alongside the prompt for informed approval.

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

