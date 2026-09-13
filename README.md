# Local OS Agent (GLaDOS)

A local-first desktop automation agent powered by local large language models (Ollama, LM Studio, or vLLM). It combines speech recognition, neural voice synthesis, and desktop tooling within an Aperture Science-themed interface and personality modeled after GLaDOS from Portal.

Designed to run locally on consumer GPUs (e.g., RTX 4070 12GB) alongside resource-heavy tasks like gaming or 3D rendering, maintaining a low memory footprint (under 3.5 GB total VRAM for both LLM and STT).

---

## Overview

The system operates across three primary layers:

1. **Agent Engine (`agent.py`)**: Connects to any OpenAI-compatible local LLM endpoint (defaulting to Ollama `glados:3b`). Enforces strict JSON execution plans, strips markdown fences, handles syntax quirks from small models, and provides a deterministic regex-based intent engine for critical desktop controls.
2. **Audio & Voice Pipeline (`voice/`)**:
   - **Speech-to-Text (`voice/listener.py`)**: GPU-accelerated OpenAI Whisper (`base.en` with FP16), constrained to under 1.0 GB VRAM via PyTorch memory fraction limits. Includes silence detection and wake word filtering (`"GLaDOS"`).
   - **Text-to-Speech (`voice/tts.py`)**: Local neural voice inference using Piper (VITS model trained on Portal assets) with Microsoft Edge Neural TTS and Windows SAPI5 as fallbacks.
   - **Acoustic Exclusion**: Prevents self-triggering by pausing audio input while the assistant is speaking.
3. **Web Management Console (`ui/`)**: A dark-mode, responsive web interface built with Three.js WebGL for 3D model rendering, real-time Server-Sent Events (SSE) telemetry, Flightradar24 tracking, and ZimaOS container controls.

---

## Architecture & Toolset

The agent exposes 28 registered tools divided across several functional domains:

### Audio & Playback Control
- `set_volume`: Sets master volume (0-100) via Windows `pycaw` linear scalar.
- `change_volume_relative`: Adjusts volume up or down by a given percentage.
- `set_app_volume`: Controls per-application audio session levels (e.g., Discord, Spotify, Chrome).
- `list_app_volumes`: Lists all active audio sessions and their current levels.
- `mute_toggle`: Toggles master system mute.
- `play_youtube`: Opens YouTube or YouTube Music searches directly in the browser.
- `media_control`: Emulates hardware multimedia keys (`play_pause`, `next_track`, `prev_track`).

### System Operations & Diagnostics
- `launch_app`: Starts native desktop applications and Windows settings protocols (`ms-settings:`).
- `get_system_stats`: Collects real-time CPU, RAM, GPU, and battery metrics via `psutil` and `torch.cuda`.
- `take_screenshot`: Captures full-resolution desktop displays to local storage.
- `minimize_all_windows`: Minimizes active windows to show the desktop.
- `lock_workstation`: Locks the Windows session immediately.
- `set_timer`: Asynchronous countdown timer that speaks an audible alert upon expiration.
- `get_clipboard` / `set_clipboard`: Reads from and writes to the Windows system clipboard.
- `read_clipboard_aloud`: Reads clipboard contents using the GLaDOS voice pipeline.

### Safety Gatekeeper
High-impact system actions require interactive user confirmation before execution:
- `kill_process`: Terminates running processes by name or PID. Includes kernel and critical service protection (PID 0, PID 4, `system`, `svchost.exe`, `csrss.exe`, `lsass.exe`, `smss.exe`, `wininit.exe`).
- `shutdown`: Schedules an operating system shutdown.
- `sleep_pc`: Places the workstation into sleep mode.
- `empty_recycle_bin`: Empties the Windows Recycle Bin without additional GUI prompts.

### Integrations
- **Steam Launcher (`tools/steam.py`)**: Auto-locates Steam installations via Windows registry, parses `libraryfolders.vdf` and app manifests across all configured drives, builds a title-to-AppID index, and uses fuzzy matching to launch games via `steam://rungameid/{app_id}`.
- **Flightradar24 Radar (`tools/flight.py`)**: Queries live public telemetry feeds for active flights (altitude, ground speed, heading, aircraft type, route, climb/descent vector) without requiring API keys.
- **ZimaOS / CasaOS Server (`tools/zimaos.py`)**: Monitors remote home server telemetry (CPU load, memory, disk usage) and manages Docker containers (Plex, Jellyfin, Nextcloud, Home Assistant).
- **Web & Information (`tools/web.py`)**: Domain alias resolution, real-time meteorological reports via `wttr.in`, and factual lookups via Wikipedia REST API.
- **Atmospheric Audio (`tools/songs.py`, `tools/sfx.py`)**: Plays Portal songs ("Still Alive", "Want You Gone") and sound effects (radio loop, sentry turret callouts) with automatic extraction from local game VPK files if present.

---

## Hardware & System Requirements

- **Operating System**: Windows 10/11 (64-bit).
- **Python**: Version 3.11 or higher.
- **GPU (Recommended)**: NVIDIA GeForce RTX GPU with CUDA support for local Whisper acceleration.
- **VRAM Budget**:
  - LLM (`glados:3b` via Ollama): ~2.2 GB
  - Whisper STT (`base.en` via CUDA): ~300 MB (hard cap set to 1024 MB)
  - Piper TTS: ~150 MB system RAM
  - Web UI & Three.js Canvas: Standard browser hardware acceleration

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Fl1pMoniz/local-os-agent.git
cd local-os-agent
```

### 2. Create and Activate a Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure the Local LLM
Ensure Ollama is installed and running:
```bash
ollama pull llama3.2:3b
ollama create glados:3b -f Modelfile
```

---

## Usage

### Interactive Terminal REPL
Launch the text console to send typed commands or run system diagnostics:
```bash
python main.py
```

### Voice Mode
Launch continuous listening mode. The assistant monitors for the wake word `"GLaDOS"` before parsing directives:
```bash
python main.py --voice
```

### Web UI
Launch the interactive browser dashboard with the 3D GLaDOS model and real-time telemetry:
```bash
python main.py --ui
```
Or start the UI server directly:
```bash
python ui/server.py
```
Open your browser at `http://127.0.0.1:5000`.

### Single Prompt Mode
Execute a single instruction non-interactively:
```bash
python main.py --prompt "Set volume to 30 percent and check system stats"
```

### Hardware Diagnostic
Verify audio endpoints, Steam library indexing, and display capture:
```bash
python main.py --test-tools
```

---

## Configuration

Environment variables can be supplied via a `.env` file or standard system variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint URL |
| `LLM_MODEL` | `glados:3b` | Target language model identifier |
| `LLM_TIMEOUT` | `45.0` | API request timeout in seconds |
| `LLM_NUM_CTX` | `2048` | Context window size (caps KV cache VRAM usage) |
| `LLM_MAX_TOKENS` | `120` | Output token generation limit for concise delivery |
| `ENABLE_TTS` | `true` | Enables or disables voice speech output |
| `TTS_VOICE` | `glados` | Voice preset (`glados`, `glados_edge`, `libby`, `aria`) |
| `STT_ENGINE` | `whisper` | Speech recognition engine (`whisper` or `google`) |
| `WHISPER_MODEL` | `base.en` | Whisper model size (`tiny.en`, `base.en`, `small.en`) |
| `WHISPER_DEVICE` | `cuda` | Hardware device for Whisper inference (`cuda` or `cpu`) |
| `WHISPER_VRAM_LIMIT_MB` | `1024` | Hard ceiling for Whisper CUDA memory allocation |
| `WAKE_WORD` | `glados` | Spoken activation keyword |
| `ZIMAOS_HOST` | `http://zimaos.local` | Hostname or IP of local ZimaOS/CasaOS server |
| `ZIMAOS_API_KEY` | `None` | Optional API token for authenticated endpoints |

---

## Testing

Run the automated test suite to verify tool execution, schema parsing, and stress handling:

```bash
python -m unittest discover tests
```

The test suite covers:
- Outermost JSON block extraction and syntax repair for small model output.
- Intent pattern matching across English and Portuguese phrasing variations.
- Protected process filtering against unauthorized kernel/system termination.
- String-to-number argument normalization for volume levels and percentages.
- Asynchronous UI state broadcasting and subscriber event delivery.
