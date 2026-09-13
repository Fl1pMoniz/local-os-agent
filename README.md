# Local OS Agent (GLaDOS)

A local-first desktop automation agent powered by local large language models (Ollama, LM Studio, or vLLM). It combines speech recognition, neural voice synthesis, and desktop tooling within an Aperture Science-themed interface and personality modeled after GLaDOS from Portal.

Designed to run locally on consumer GPUs (e.g., RTX 4070 12GB) alongside resource-heavy tasks like gaming or 3D rendering, maintaining a low memory footprint (under 3.5 GB total VRAM for both LLM and STT).

---

## Quickstart Launchers: `glados` & `glados-web`

For seamless daily operation on Windows, two launcher scripts are provided in the repository root:

### 1. `glados` (Clinical CLI Terminal)
Runs the terminal console in pure text mode:
```powershell
# Interactive CLI REPL
.\glados

# Voice Listener Mode (Microphone + Neural Speech)
.\glados --voice

# Single Directive Execution
.\glados "clip that"
.\glados "ai stats"
.\glados "flight AA100"
.\glados "server ssh"
```
* **Automated Pre-Flight Check**: Checks if your local LLM server (`localhost:11434`) is reachable; if offline, automatically spawns `ollama serve` in the background before launching.
* **Pure CLI Text Mode**: Suppresses audio output when running via `glados` for an authentic, silent terminal experience.

### 2. `glados-web` (Aperture Web Console)
Launches the full 3-column browser console at `http://127.0.0.1:5000`:
```powershell
.\glados-web
```
* Automatically verifies the Ollama server, starts the local HTTP/SSE backend on port 5000, and opens your default browser.
* Features a 3-column layout:
  * **Left Column**: Live command terminal with real-time streaming output and prompt input.
  * **Middle Column**: Aperture Directive Matrix in pure ASCII with interactive, clickable shortcuts.
  * **Right Column**: Live component telemetry cards (`[PC STATS & HARDWARE]` with the GLaDOS AI Neural Core HUD, `[ZIMAOS REMOTE SERVER]`, and the ADS-B Airspace Radar).

---

## Core System Architecture

1. **Agent Engine (`agent.py`)**: Connects to any OpenAI-compatible local LLM endpoint (defaulting to Ollama `glados:3b`). Enforces strict JSON execution plans, strips markdown fences, repairs syntax quirks, tracks token metrics, and provides a deterministic regex intent engine for mission-critical desktop controls.
2. **Audio & Voice Pipeline (`voice/`)**:
   * **Speech-to-Text (`voice/listener.py`)**: GPU-accelerated OpenAI Whisper (`base.en` with FP16), constrained to under 1.0 GB VRAM via PyTorch memory fraction limits. Includes silence detection and phonetic wake word filtering (`"GLaDOS"`).
   * **Text-to-Speech (`voice/tts.py`)**: Local neural voice inference using Piper (VITS model trained on Portal game assets) with Microsoft Edge Neural TTS and Windows SAPI5 fallbacks.
   * **Acoustic Exclusion**: Pauses audio input while speaking to prevent self-triggering feedback loops.
3. **Web Management Console (`ui/`)**: Built with responsive grid styling, real-time Server-Sent Events (SSE) telemetry, interactive directive matrices, and live ASCII hardware monitors.

---

## Protocols & Registered Toolset

The agent exposes 43 registered tools divided across specialized Aperture protocols:

### Protocol 1: Aperture Media Dispatcher (Jellyfin)
* `search_and_play_jellyfin(query)`: Queries movies, series, or albums hosted on your local ZimaOS Jellyfin container (`http://192.168.1.123:8097`) and opens streaming playback.
* `get_jellyfin_now_playing()`: Generates a live ASCII Now Playing HUD displaying active streams, titles, media type, and playback progress.

### Protocol 2: 30-Second Gameplay Clipper & OBS FOSS Integration
* `capture_game_clip(seconds=30)`: Triggers OBS Studio's Replay Buffer via native OBS WebSocket (`SaveReplayBuffer`) or hardware GPU encoder (NVIDIA ShadowPlay `Alt+F10`) to archive highlights. Automatically detects active game metadata and discovers newly written `.mp4` and `.mkv` files across game subdirectories (Windows Game Bar dependency completely removed).
* `launch_obs(start_buffer=True)`: Launches OBS Studio in the background or minimized to tray with the Replay Buffer primed and WebSocket active.
* `list_recent_clips(limit=5)`: Lists recently captured gameplay highlights, timestamps, and file sizes.

### Protocol 3: Optical Screen Vision & Error Inspection
* `analyze_screen(prompt)`: Captures the active monitor and uses visual AI (Google Gemini 2.5 Flash Vision or local multimodal model) to diagnose stack traces, compiler errors, IDE bugs, code reviews, or deliver a witty roast of the desktop.

### Protocol 4: Smart Audio Ducking & Acoustic Synthesizer
* `attenuate_background_audio(duck_pct=0.2)` / `restore_background_audio()`: Smoothly ducks background application audio (Spotify, games, Discord) to 20% volume during GLaDOS speech synthesis using Windows Core Audio (`pycaw`), restoring normal levels when finished.
* `play_soundboard(clip_name)`: Plays explicit character dialogue (Cave Johnson lemons speech, Wheatley quotes, Sentry Turrets, Space Core, Neurotoxin).
  > [!NOTE]
  > **Conversational Accuracy**: Inquiring about characters (e.g., *"Who is Cave Johnson?"*, *"Tell me about Wheatley"*) produces thoughtful conversational AI answers delivered by GLaDOS in character. Voiceline clips are only played when explicitly requested (e.g., *"play a Cave Johnson voiceline"*, *"play Wheatley voiceline"*, *"soundboard lemons"*).

### Protocol 5: ZimaOS Remote Server & SSH Shell Integration
* `get_zimaos_status`: Monitors remote ZimaOS/CasaOS server CPU, RAM, disk usage, and host uptime.
* `list_zimaos_apps`: Discovers running Docker containers and services.
* `launch_zimaos_app(app_name)`: Opens containerized web interfaces (Jellyfin, Plex, Nextcloud, Home Assistant).
* `open_zimaos_dashboard`: Launches the main ZimaOS web management GUI.
* `open_zimaos_ssh()`: Spawns a dedicated SSH terminal console (`fl1pmoniz@192.168.1.123`).
* `monitor_zimaos(live=True)`: Continuous in-terminal live ASCII telemetry HUD.
* `set_zimaos_host(new_host)`: Reconfigures and persists the remote server IP address.

### Protocol 6: Discord Mobile Relay & Clip Sharing
* `send_clip_to_discord(clip_path)`: Directly uploads the latest 30-second gameplay clip (up to 25 MB) to your Discord channel via webhook, tagged with the active game name.
  > [!TIP]
  > **Channel Destination**: Discord webhooks are channel-bound. GLaDOS posts to whichever text channel the webhook was created in (e.g. `#clips` or `#highlights`). Configure your webhook once using `set_discord_webhook <url>`.
* `set_discord_webhook(webhook_url)`: Securely saves and persists your Discord webhook in `captures/discord_config.json`.
* `send_discord_alert(title, message)`: Dispatches embedded text alerts and hardware notifications to Discord.

### Protocol 7: Subject Compliance & Wellness HUD
* `check_subject_status()`: Displays the Aperture Subject Biometric HUD with testing session duration, ergonomic posture assessment, 20-20-20 eye strain tracker, and hydration level.
* `log_water_intake(milliliters=250)`: Logs water consumption events into the subject's biological testing registry.

---

## Live Hardware Telemetry & GLaDOS AI Neural Core HUD

Running `hw`, `ai stats`, or `hw live` renders a unified, 70-character Aperture Science ASCII HUD displaying both host hardware and the local AI engine:

```text
+====================================================================+
|   APERTURE SCIENCE COMPONENT TELEMETRY & LIVE HARDWARE MONITOR     |
| [* TELEMETRY ACTIVE] Polling Sensors...       Refresh: every 1.5s  |
| Press Ctrl+C at any time to return to GLaDOS-CLI console           |
+====================================================================+
+--------------------------------------------------------------------+
|           APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD        |
+--------------------------------------------------------------------+
| CPU Model         : AMD Ryzen 7 5700X 8-Core Processor             |
| CPU Utilization   :  28.4% [████░░░░░░░░░░] @ 3.40 GHz             |
| CPU Temperature   :  48.2°C (Operational Thermal Range)            |
| System Memory     :  24.8 / 31.89 GB (77.6%) [███████████░░░]      |
| GPU Model         : NVIDIA GeForce RTX 4070                        |
| GPU Utilization   :   8.0% [█░░░░░░░░░░░░░]                        |
| GPU Temperature   :  46.0°C (Thermal Headroom: Optimal)            |
| VRAM Usage        : 5,588 / 12,282 MB (45.5%) [██████░░░░░░░░]     |
| Active Power Draw :  37.2 W (NVIDIA Board Power Sensor)            |
| System Disk (C:)  : 842.9 / 930.6 GB (90.6%) [█████████████░]      |
| Host OS & Uptime  : Windows 11 (Uptime: 19h 20m | 392 Proc)        |
+--------------------------------------------------------------------+
|            GLaDOS AI NEURAL CORE & INFERENCE TELEMETRY             |
+--------------------------------------------------------------------+
| Neural Engine     : glados:3b (3.2B Q4_K_M) [* ONLINE]             |
| AI RAM Footprint  : 1,154.1 MB (Ollama: 1,131.4M | Host: 22.7M)    |
| Model VRAM Alloc  : 2,962 MB (Dedicated Tensor Weights)            |
| Session Tokens    : 15,248 produced (In: 14,949 | Out: 299)        |
| Generation Rate   :  38.4 tok/s [████████░░░░] (Peak: 42.1)        |
| Inference Latency : 145 ms (Avg Session Speed: 36.2 tok/s)         |
| Context Window    : 348 / 8,192 tok (4.2%) [░░░░░░░░░░░░]          |
| Aperture Subsystem: Voice: Piper VITS | Vision: Optical Online     |
+--------------------------------------------------------------------+
```

### Monitored AI Core Metrics
* **AI RAM Footprint**: Live process memory scan via `psutil` isolating Ollama/llama-server runtime memory from the GLaDOS agent process.
* **Tokens Produced**: Cumulative session tokens (input prompts vs output completion).
* **Generation Rate**: Real-time throughput (`tok/s`), peak velocity, and session average.
* **Context Allocation**: Active tokens versus allocated context window capacity.
* **Subsystem Status**: Piper VITS neural voice engine and optical screen vision availability.

---

## Desktop Automation & Safety Gatekeeper

* **Audio Control**: `set_volume`, `change_volume_relative`, `mute_toggle`, `set_app_volume`, `list_app_volumes`.
* **Media Keys**: `play_youtube`, `media_control` (`play_pause`, `next_track`, `prev_track`).
* **Steam Launcher (`tools/steam.py`)**: Registry-detected Steam paths, parses `libraryfolders.vdf` and app manifests across drives, uses fuzzy matching, and launches via `steam://rungameid/{app_id}`.
* **Airspace Radar (`tools/flight.py`)**: Real-time ADS-B radar tracking via Flightradar24 telemetry HUD (`flight <callsign>`, `track_flight`).
* **System Operations**: `launch_app`, `get_system_stats`, `take_screenshot`, `minimize_all_windows`, `lock_workstation`, `set_timer`, `get_clipboard`, `set_clipboard`.
* **Safety Gatekeeper**: Destructive actions (`kill_process`, `shutdown`, `sleep_pc`) require interactive confirmation with contextual reasoning displayed before execution. Protected kernel and critical Windows processes (PID 0, 4, `csrss.exe`, `svchost.exe`, etc.) cannot be killed.

---

## Configuration

Settings can be customized via `.env` or system environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint URL |
| `LLM_MODEL` | `glados:3b` | Target language model identifier |
| `LLM_TIMEOUT` | `45.0` | API request timeout in seconds |
| `LLM_NUM_CTX` | `2048` | Context window size (caps KV cache VRAM footprint) |
| `LLM_MAX_TOKENS` | `120` | Output token generation limit for concise delivery |
| `ENABLE_TTS` | `true` | Enables or disables voice speech output |
| `TTS_VOICE` | `glados` | Voice preset (`glados`, `glados_edge`, `libby`, `aria`) |
| `STT_ENGINE` | `whisper` | Speech recognition engine (`whisper` or `google`) |
| `WHISPER_MODEL` | `base.en` | Whisper model size (`tiny.en`, `base.en`, `small.en`) |
| `WHISPER_DEVICE` | `cuda` | Hardware device for Whisper inference (`cuda` or `cpu`) |
| `WHISPER_VRAM_LIMIT_MB` | `1024` | Hard ceiling for Whisper CUDA memory allocation |
| `WAKE_WORD` | `glados` | Spoken activation keyword |
| `DISCORD_WEBHOOK_URL` | `None` | Discord webhook URL for clip uploads & alerts |
| `ZIMAOS_HOST` | `http://192.168.1.123` | Hostname or IP of local ZimaOS server |
| `JELLYFIN_URL` | `http://192.168.1.123:8097` | Direct URL to ZimaOS Jellyfin media container |
| `GEMINI_API_KEY` | `None` | Optional API key for Google Gemini 2.5 Flash Vision |

---

## Testing

Run the automated test suite to verify tool execution, schema parsing, and protocol safety:

```powershell
python -m unittest discover tests
```

The test suite covers **110 unit tests** spanning:
* Outermost JSON block extraction and syntax repair for small model outputs.
* Intent pattern matching across English and Portuguese phrasing variations.
* Voiceline triggering: explicit playback commands execute soundboard clips, while general inquiries about Cave Johnson or Wheatley generate conversational AI answers.
* Fast AI RAM process discovery, token tracking, and 70-column ASCII HUD card formatting.
* Media dispatching, 30s game clip capture, Discord webhook posting, and wellness tracking.
* Web UI endpoints, SSE terminal events, and audio ducking.
