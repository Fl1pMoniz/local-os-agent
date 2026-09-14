# GLaDOS Local OS Agent - Beginner's Architectural Guide & Code Walkthrough

Welcome to the architectural learning guide for the GLaDOS Local OS Agent! If you are a beginner or intermediate programmer looking to understand how a modern, production-grade, cross-platform AI assistant works under the hood, this document is designed for you.

This guide breaks down the core software engineering concepts, walks through the codebase step by step, and explains both high-level design patterns and specific Python functions.

---

## Table of Contents
1. [The Big Picture: What is an OS Agent?](#1-the-big-picture-what-is-an-os-agent)
2. [Software Architecture: Why Hexagonal Architecture?](#2-software-architecture-why-hexagonal-architecture)
3. [Project Directory Tour](#3-project-directory-tour)
4. [Core Concepts & Code Deep Dive](#4-core-concepts--code-deep-dive)
   - [A. Inversion of Control & Dependency Injection (`app/core/`)](#a-inversion-of-control--dependency-injection-appcore)
   - [B. Ports & Protocols (`app/ports/`)](#b-ports--protocols-appports)
   - [C. Concrete Adapters (`app/adapters/`)](#c-concrete-adapters-appadapters)
   - [D. 12-Factor Configuration (`app/core/config.py`)](#d-12-factor-configuration-appcoreconfigpy)
   - [E. The Agent Brain: Tool Calling & Fallbacks (`app/agent/`)](#e-the-agent-brain-tool-calling--fallbacks-appagent)
   - [F. The Audio & Voice Pipeline (`voice/`)](#f-the-audio--voice-pipeline-voice)
   - [G. Desktop Automation Tools (`tools/`)](#g-desktop-automation-tools-tools)
   - [H. Real-Time Web Console & Server-Sent Events (`ui/`)](#h-real-time-web-console--server-sent-events-ui)
5. [End-to-End Execution Walkthroughs](#5-end-to-end-execution-walkthroughs)
   - [Trace 1: Setting System Volume](#trace-1-setting-system-volume)
   - [Trace 2: Spoken Flight Tracking via Voice](#trace-2-spoken-flight-tracking-via-voice)
6. [Glossary of Senior Engineering Terms](#6-glossary-of-senior-engineering-terms)

---

## 1. The Big Picture: What is an OS Agent?

A standard chatbot (like basic ChatGPT) takes text input and returns text output. It cannot interact with your computer.

An **OS Agent** (Operating System Agent) bridges the gap between language models and your operating system. It listens to commands, decides what actions need to happen, and executes real system calls (changing volume, finding games, taking screenshots, querying homelab servers, or managing windows).

### The Feedback Loop
```text
  User Input (Voice / CLI / Web UI)
                 │
                 ▼
       Brain (LLM / Fallback)
                 │
  (Decides action: e.g. set_volume)
                 │
                 ▼
    OS Port (Interface Contract)
                 │
                 ▼
 Concrete Adapter (Windows / Linux / Mock)
                 │
                 ▼
      Operating System Action
                 │
                 ▼
 Feedback (Speech / Amber CRT Web / Terminal)
```

### How Does an LLM "Click Buttons"?
Large Language Models cannot actually click mice or run code on their own. Instead, we use a pattern called **Tool Calling** (or Function Calling).
1. We give the LLM a list of tools it can use, describing what each tool does and what arguments it accepts (e.g. `set_volume(level: int)`).
2. When the user says *"Make it louder"*, the LLM does not just reply with conversational text. It responds with structured JSON:
   ```json
   {
     "tool": "change_volume_relative",
     "args": {"delta": 10}
   }
   ```
3. Our Python code parses this JSON, runs our Python function `change_volume_relative(delta=10)`, and reports the result back to the LLM.

---

## 2. Software Architecture: Why Hexagonal Architecture?

In beginner projects, code is often tightly coupled:
```python
# Tightly coupled (anti-pattern):
import ctypes  # Crashes instantly if imported on Linux!

def lock_screen():
    ctypes.windll.user32.LockWorkStation()
```
If you run that script on Ubuntu or inside a Docker container, it immediately crashes with:
`AttributeError: module 'ctypes' has no attribute 'windll'`

To solve this, senior engineers use **Hexagonal Architecture** (also known as **Ports and Adapters**):

### The Analogy: The USB Port
Think of your computer's USB port:
- The **Port** is the physical socket specification. It defines voltage, pin layouts, and communication protocols.
- The **Adapter** is whatever device you plug into it: a mouse, a flash drive, or a game controller.
- Your computer motherboard does not care *what brand* of mouse you plug in, as long as it adheres to the USB protocol.

In GLaDOS:
- A **Port** (`app/ports/`) is a Python `Protocol` that defines *what* can be done (e.g., `AudioPort` defines `set_master_volume(volume: float)`).
- An **Adapter** (`app/adapters/`) is the actual implementation:
  - On Windows: `WindowsAudioAdapter` calls Windows CoreAudio via `pycaw`.
  - On Linux: `LinuxAudioAdapter` calls PipeWire via `wpctl` or PulseAudio via `pactl`.
  - In Headless/CI tests: `NullAudioAdapter` simulates success without touching any real hardware.
- The Agent Core only talks to the **Port**. It never knows (or cares) which OS is running!

---

## 3. Project Directory Tour

Here is how the project is structured:

```text
local-os-agent/
├── pyproject.toml              # Project dependencies, build config, and pytest markers
├── .pre-commit-config.yaml     # Git pre-commit hooks for automated linting & formatting
├── AGENTS.md                   # Developer rules and guidelines for AI and human contributors
├── README.md                   # Setup guide and usage instructions
├── BEGINNER_GUIDE.md           # This comprehensive tutorial document
├── glados                      # Linux/macOS executable launcher (bash)
├── glados-web                  # Linux/macOS Web UI launcher (bash)
├── glados.bat                  # Windows CLI launcher
├── glados-web.bat              # Windows Web UI launcher
│
├── app/                        # Modern Hexagonal Architecture layer
│   ├── core/                   # Container, DI modules, 12-factor config, dual-channel logging
│   ├── ports/                  # Pure interfaces (typing.Protocol contracts)
│   ├── adapters/               # Concrete implementations (windows, linux, common, mock)
│   ├── agent/                  # LangChain tool-calling engine, Pydantic schemas, offline fallbacks
│   └── presentation/           # Monospaced ASCII HUD cards and console status formatters
│
├── tools/                      # Underlying tool implementations (audio, system, flight, zimaos, etc.)
├── voice/                      # Voice pipeline (Whisper STT, Piper TTS, audio arbiter)
├── ui/                         # Amber CRT Retro Terminal Web UI (HTTP server & SSE dispatch)
└── tests/                      # Pytest automated test suite (149 test cases)
```

---

## 4. Core Concepts & Code Deep Dive

### A. Inversion of Control & Dependency Injection (`app/core/`)

**Inversion of Control (IoC)** means you do not instantiate dependencies directly inside your classes with `adapter = WindowsAudioAdapter()`. Instead, a central **Container** provides the appropriate instance.

We use the `injector` library. Look at [`app/core/modules.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/core/modules.py):

```python
class PlatformModule(Module):
    def configure(self, binder: Binder) -> None:
        if self.settings.headless_mode:
            # When running headless or in CI, bind mock adapters
            binder.bind(AudioPort, to=NullAudioAdapter, scope=singleton)
        elif sys.platform == "win32":
            # On Windows, bind Windows CoreAudio
            binder.bind(AudioPort, to=WindowsAudioAdapter, scope=singleton)
        elif sys.platform.startswith("linux"):
            # On Linux, bind PipeWire / PulseAudio
            binder.bind(AudioPort, to=LinuxAudioAdapter, scope=singleton)
```

To use audio anywhere in the application, you simply ask the container:
```python
from app.core.container import get_container
from app.ports.audio import AudioPort

container = get_container()
audio_service = container.get(AudioPort)
audio_service.set_master_volume(0.5)  # Works on Windows, Linux, or headless!
```

---

### B. Ports & Protocols (`app/ports/`)

In older Python, people used Abstract Base Classes (`abc.ABC`). In modern Python 3.10+, we use `typing.Protocol` (structural subtyping or "static duck typing").

Look at [`app/ports/audio.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/ports/audio.py):

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class AudioPort(Protocol):
    def duck_audio(self, target_volume: float = 0.2) -> bool:
        """Ducks background application audio during speech synthesis."""
        ...

    def restore_audio(self) -> bool:
        """Restores previously ducked audio levels."""
        ...

    def get_master_volume(self) -> float:
        """Returns current master volume between 0.0 and 1.0."""
        ...

    def set_master_volume(self, volume: float) -> bool:
        """Sets the system master output volume."""
        ...
```

**Why `...` (Ellipsis)?**
In a Protocol, the methods have no body (`...`). They define the *contract*: any class that has these methods with matching parameters automatically satisfies `AudioPort` without needing to explicitly inherit from it.

---

### C. Concrete Adapters (`app/adapters/`)

Let us compare how the same method is implemented differently across platforms:

#### 1. Windows Implementation ([`app/adapters/windows/audio.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/adapters/windows/audio.py))
Uses `pycaw` (Python Core Audio Windows) to speak directly to the Windows Audio Session API:
```python
def set_master_volume(self, volume: float) -> bool:
    endpoint = self._get_endpoint()
    bounded = max(0.0, min(1.0, volume))
    endpoint.SetMasterVolumeLevelScalar(bounded, None)
    return True
```

#### 2. Linux Implementation ([`app/adapters/linux/audio.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/adapters/linux/audio.py))
Uses standard Linux command-line utilities like `wpctl` (PipeWire) or `pactl` (PulseAudio):
```python
def set_master_volume(self, volume: float) -> bool:
    bounded = max(0.0, min(1.0, volume))
    if self._has_wpctl:
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{bounded:.2f}"])
        return True
    elif self._has_pactl:
        percent = int(bounded * 100)
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        return True
    return False
```

#### 3. Single-Instance File Locking ([`app/adapters/common/file_lock.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/adapters/common/file_lock.py))
In early versions, Windows used `ctypes.windll.kernel32.CreateMutexW` to prevent two GLaDOS instances from running simultaneously.
We replaced that with cross-platform advisory file locking using `portalocker`:
```python
def acquire(self) -> bool:
    self._lock_file = open(self._lock_path, "a+")
    # portalocker works on Windows, Linux, and macOS:
    portalocker.lock(self._lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
    return True
```
If another GLaDOS process is already open, `acquire()` cleanly returns `False` instead of crashing.

---

### D. 12-Factor Configuration (`app/core/config.py`)

In production software, you should never hardcode configuration values (like IP addresses, ports, or API keys). The [Twelve-Factor App methodology](https://12factor.net/config) dictates storing configuration in environment variables.

In [`app/core/config.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/core/config.py), we use Pydantic's `BaseSettings`:

```python
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="GLADOS_HOST")
    port: int = Field(default=5000, alias="GLADOS_PORT")
    headless_mode: bool = Field(default=False, alias="GLADOS_HEADLESS")
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="glados:3b", alias="LLM_MODEL")
```

**How this helps you:**
- By default, `settings.port` is `5000`.
- If someone sets an environment variable `GLADOS_PORT=8080`, Pydantic automatically parses and converts it to the integer `8080`.
- If someone provides an invalid value like `GLADOS_PORT="invalid"`, Pydantic raises a clear validation error immediately on startup before errors cascade.

---

### E. The Agent Brain: Tool Calling & Fallbacks (`app/agent/`)

The agent subsystem coordinates how instructions are resolved into code execution:

#### 1. The Offline Survival Fallback (`app/agent/fallback.py`)
Why query an AI model across the network just to mute your sound?
If your computer is blasting music at 2 AM or your LLM server takes 10 seconds to respond, you need instant reaction time.

[`app/agent/fallback.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/app/agent/fallback.py) uses anchored regular expressions to catch immediate survival commands:
```python
RE_MUTE = re.compile(r"^(?:mute|unmute|silenciar|mudo|mutar|desmutar)$", re.IGNORECASE)
RE_STOP = re.compile(r"^(?:stop|stop song|shut up|parar|silence)$", re.IGNORECASE)
RE_LOCK = re.compile(r"^(?:lock|lock screen|lock workstation|trancar tela)$", re.IGNORECASE)
```
If a user inputs `"mute"`, the resolver triggers immediately with **zero latency** and zero LLM calls.

#### 2. LangChain Tools & Pydantic Validation (`app/agent/tools.py`)
For complex natural language, we register tools with LangChain using `@tool` and Pydantic parameter schemas:
```python
class VolumeInput(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Master audio volume (0 to 100).")

@tool(args_schema=VolumeInput)
def set_volume_tool(level: int) -> str:
    """Sets master system volume percentage (0 to 100)."""
    success, msg = audio.set_volume(level)
    return msg
```
If the LLM hallucinates an invalid level like `level: 999`, Pydantic catches it immediately, preventing invalid system calls.

---

### F. The Audio & Voice Pipeline (`voice/`)

GLaDOS has full duplex voice capability:
1. **Speech Recognition (`voice/listener.py`)**: Uses OpenAI's Whisper model (`base.en`) running locally on your GPU (CUDA) or CPU.
   - It captures raw audio from your microphone using `sounddevice` or `pyaudio`.
   - It measures the Root Mean Square (RMS) volume to distinguish speaking from room silence.
   - It transcribes speech to text and checks for the wake word: `"glados"`.
2. **Speech Synthesis (`voice/tts.py`)**: Uses Piper (a fast, local neural text-to-speech engine running via ONNX runtime) trained on Ellen McLain's GLaDOS voice lines.
3. **The Feedback Loop Problem & Acoustic Arbiter (`voice/audio_arbiter.py`)**:
   - What happens if GLaDOS speaks while her microphone is active? She will hear her own voice, transcribe it, and start replying to herself indefinitely!
   - To prevent this, `GLOBAL_AUDIO_LOCK` coordinates with `audio_ducking.py`:
     - Before GLaDOS speaks, the listener microphone is paused.
     - Background music (Spotify, Chrome) is ducked to 20% volume.
     - GLaDOS speaks her line.
     - Background music is restored to 100%.
     - The microphone listener is unpaused.

---

### G. Desktop Automation Tools (`tools/`)

All 43 desktop capabilities are modularized in the `tools/` directory. Here are three highlights:

1. **Steam Game Discovery ([`tools/steam.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/tools/steam.py))**:
   - Parses the Valve Data Format (`libraryfolders.vdf`) to locate all Steam libraries across all storage drives (`C:`, `D:`, `E:`).
   - Reads every `appmanifest_<id>.acf` file to build a real-time dictionary of installed game titles.
   - Uses `difflib.get_close_matches` so saying *"launch cyber punk"* correctly launches App ID `1091500` (*Cyberpunk 2077*).
2. **ADS-B Airspace Radar ([`tools/flight.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/tools/flight.py))**:
   - Fetches live commercial flight coordinates, calculates Great-Circle distance using the Haversine trigonometric formula, predicts landing time, and formats an authentic monospaced ASCII radar screen.
3. **OBS Studio Replay Buffer ([`tools/game_clipper.py`](file:///c:/Users/fiui2/OneDrive/Documentos/PROJETOSPROGRAM/local-os-agent/tools/game_clipper.py))**:
   - Connects to OBS Studio via WebSocket v5.
   - Dispatches `SaveReplayBuffer` to flush the last 30 seconds of video memory to an `.mp4` file.
   - Uses `tools/discord_relay.py` to upload the clip directly to a Discord channel.

---

### H. Real-Time Web Console & Server-Sent Events (`ui/`)

The web UI is rendered as a retro Amber CRT Terminal:
- The backend runs a lightweight Python HTTP server (`ui/server.py`).
- Instead of complex bidirectional WebSockets, it uses **Server-Sent Events (SSE)** at `/events`.
- SSE is a standard web technology where the browser opens a persistent HTTP connection and the Python backend pushes updates as single-line streams:
  ```text
  data: {"state": "speaking", "text": "Testing is mandatory."}
  ```
- The frontend JavaScript (`ui/index.html`) listens via `EventSource`:
  ```javascript
  const evtSource = new EventSource("/events");
  evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      updateTerminal(data);
  };
  ```

---

## 5. End-to-End Execution Walkthroughs

### Trace 1: Setting System Volume
What happens when you type `"set volume to 50"`?

```text
1. Terminal / Web Input: User submits "set volume to 50"
2. app/agent/langchain_agent.py: Receives prompt
3. app/agent/fallback.py: RE_VOL_EXACT matches "set volume to 50"
4. Match found: tool="set_volume", args={"level": 50}
5. Container resolves AudioPort -> WindowsAudioAdapter (on Windows)
6. WindowsAudioAdapter calls pycaw -> endpoint.SetMasterVolumeLevelScalar(0.5)
7. Console & Web UI: Logs "[+] Master volume adjusted to 50 percent."
```

### Trace 2: Spoken Flight Tracking via Voice
What happens when you say: *"GLaDOS, track flight DL450"*?

```text
1. Microphone captures audio waveform via sounddevice
2. voice/listener.py: Energy exceeds threshold -> silence detected -> audio chunk finalized
3. Whisper model transcribes chunk -> "glados track flight dl450"
4. Wake word detected: query isolated -> "track flight dl450"
5. Offline fallback checks prompt -> No survival match -> forwards to LangChain
6. LangChain calls ChatOpenAI with prompt and 43 registered tools
7. LLM returns ToolCall: track_flight_tool(flight_query="DL450")
8. tools/flight.py: Queries flight coordinates, calculates ETA, formats ASCII HUD
9. voice/audio_arbiter.py: Pauses microphone, ducks background audio
10. voice/tts.py: Piper speaks: "Aperture Science radar tracking active for DL450."
11. Web UI: Updates radar tile with monospaced telemetry table
12. Audio restored to normal volume; microphone listener unpaused
```

---

## 6. Glossary of Senior Engineering Terms

| Term | Meaning in this Project |
| :--- | :--- |
| **Port** | An abstract interface (`Protocol`) describing *what* can be done without specifying *how*. |
| **Adapter** | A concrete class implementing a Port for a specific operating system or external service. |
| **Inversion of Control (IoC)** | Delegating the creation and lifetime of objects to a central registry (`injector`). |
| **Dependency Injection (DI)** | Providing objects with their required dependencies rather than creating them internally. |
| **12-Factor App** | Methodology for building clean cloud/local software; emphasizes config in environment variables. |
| **Server-Sent Events (SSE)** | Unidirectional HTTP streaming protocol for real-time server-to-browser telemetry. |
| **Audio Ducking** | Automatically attenuating background audio volume during voice notifications or speech. |
| **Pydantic** | Python data validation library using type annotations to enforce runtime constraints. |
| **Advisory File Lock** | Kernel/filesystem lock preventing multiple instances of a program from executing concurrently. |
| **Mocking** | Replacing real hardware or external APIs with controllable test objects during unit testing. |

---

*Enjoy exploring and learning from the codebase! If you have any questions, inspect the corresponding tests in the `tests/` directory to see each module verified in isolation.*
