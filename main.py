"""CLI Runner and Interactive REPL for the Local OS Agent."""

import argparse
import ctypes
import logging
import sys
import time
from typing import Any

from agent import OSAgent
from config import config
from schemas import AgentResponse, ToolAction, ToolExecutionResult
from tools import execute_tool, list_tools
from tools.steam import discover_installed_steam_games

_mutex_handle = None


def acquire_single_instance_lock() -> bool:
    """Ensures only a single instance of GLaDOS can run on the system to prevent audio echo."""
    global _mutex_handle
    try:
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        mutex_name = "Local\\ApertureOS_GLaDOS_SingleInstance_Mutex"
        _mutex_handle = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            print("\n" + "=" * 65)
            print(" [!] NOTICE: GLaDOS is already running in another window.")
            print("     To prevent voice echoing and duplicate processes,")
            print("     this duplicate instance has exited.")
            print("=" * 65 + "\n")
            return False
        return True
    except Exception:
        return True

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("local_os_agent")

# Suppress noisy HTTP and network libraries (httpx, httpcore, urllib3, openai) to ensure clean CLI output
for _noisy in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


def print_banner() -> None:
    banner = r"""
   ____ _             _  ___  ____  
  / ___| | __ _  __| |/ _ \/ ___| 
 | |  _| |/ _` |/ _` | | | \___ \ 
 | |_| | | (_| | (_| | |_| |___) |
  \____|_|\__,_|\__,_|\___/|____/ 
==================================================
               Aperture Science AI
==================================================
"""
    print(banner)


def check_llm_connection(agent: OSAgent) -> bool:
    """Verifies that the configured local LLM endpoint is reachable."""
    try:
        models_resp = agent.client.models.list()
        available = [m.id for m in models_resp.data] if hasattr(models_resp, "data") else []
        print(f"[+] Successfully connected to LLM at {agent.base_url}")
        if available:
            print(f"    Available models: {', '.join(available[:5])}")
        return True
    except Exception as e:
        print(f"[!] Warning: Could not connect to local LLM at {agent.base_url}: {e}")
        print("    Ensure Ollama ('ollama run llama3.2') or LM Studio local server is active.")
        return False


def run_diagnostic() -> None:
    """Run non-destructive hardware and toolset diagnostic."""
    print("\n--- Running Local OS Agent Diagnostic ---")

    print("\n1. Registered Tools:")
    tools = list_tools()
    for name, tool_def in tools.items():
        sens = " [SENSITIVE - REQUIRES CONFIRMATION]" if tool_def.sensitive else ""
        print(f"  * {name}: {tool_def.description}{sens}")

    print("\n2. Steam Discovery Check:")
    try:
        games = discover_installed_steam_games()
        if games:
            print(f"  [+] Discovered {len(games)} installed Steam game(s):")
            for name, appid in list(games.items())[:8]:
                print(f"      - {name} (AppID: {appid})")
            if len(games) > 8:
                print(f"      ... and {len(games) - 8} more.")
        else:
            print("  [i] No Steam installation or games discovered.")
    except Exception as e:
        print(f"  [!] Steam discovery error: {e}")

    print("\n3. System Stats Test:")
    try:
        res = execute_tool("get_system_stats")
        print(f"  [+] Stats: {res.data}")
    except Exception as e:
        print(f"  [!] Stats error: {e}")

    print("\n4. Screenshot Test:")
    try:
        res = execute_tool("take_screenshot", {"filename": "diagnostic_test.png"})
        print(f"  [+] Screenshot: {res.message}")
    except Exception as e:
        print(f"  [!] Screenshot error: {e}")

    print("\n--- Diagnostic Finished ---\n")


def execute_and_display(agent: OSAgent, prompt: str, interactive: bool = False, source: str = "cli") -> None:
    """Run a prompt through the agent and format execution results."""
    print(f"\n[User Query]: {prompt}")
    print("Thinking...")

    try:
        from ui.state import ui_state
        ui_state.update(state="thinking", thought="Formulating execution plan...", text="")
    except Exception:
        pass

    try:
        plan = agent.query_llm(prompt)
        print(f"\n[Agent Thought]: {plan.thought}")

        if plan.response:
            print(f"\n[GLaDOS]: \"{plan.response}\"")
            try:
                from ui.state import ui_state
                ui_state.update(state="speaking", text=plan.response)
            except Exception:
                pass
            if config.voice_enabled:
                from voice import speak
                speak(plan.response, wait=True)
                time.sleep(0.35)  # Acoustic room decay cooldown

        if not plan.actions:
            try:
                from ui.state import ui_state
                resp_txt = plan.response or plan.thought or ""
                ui_state.record_terminal_event(source=source, command=prompt, output=f"[GLaDOS]: \"{resp_txt}\"", response=resp_txt)
            except Exception:
                pass
            return

        print(f"[Actions to Execute]: {len(plan.actions)}")
        for idx, action in enumerate(plan.actions, 1):
            args_str = ", ".join(f"{k}={v!r}" for k, v in action.args.items())
            print(f"  {idx}. {action.tool}({args_str})")

        print("\n[Execution Progress]:")

        def on_start(a: ToolAction):
            print(f"  -> Running {a.tool}...", end="", flush=True)

        def on_finish(r: ToolExecutionResult):
            icon = "+" if r.success else ("!" if r.status == "cancelled" else "x")
            print(f" [{icon}] Status: {r.status} - {r.message}")
            if isinstance(r.data, dict) and "terminal_card" in r.data:
                print(f"\n{r.data['terminal_card']}\n")
            elif r.tool in ("get_system_stats", "monitor_hardware") and isinstance(r.data, dict) and "hud_card" in r.data:
                print(f"\n{r.data['hud_card']}\n")
            elif r.tool in ("get_zimaos_status", "monitor_zimaos"):
                from tools.zimaos import get_zimaos_telemetry
                t = r.data if isinstance(r.data, dict) and "hud_card" in t else get_zimaos_telemetry()
                if isinstance(t, dict) and "hud_card" in t:
                    print(f"\n{t['hud_card']}\n")

        results = agent.execute_plan(plan, on_action_start=on_start, on_action_finish=on_finish)
        print("\nAll actions completed.")

        try:
            from ui.state import ui_state
            resp_text = plan.response or plan.thought or "Directive executed."
            lines = []
            if resp_text:
                lines.append(f"[GLaDOS]: \"{resp_text}\"")
            for r in results:
                icon = "+" if r.success else "x"
                lines.append(f"  [{icon}] {r.tool}: {r.message}")
                if isinstance(r.data, dict) and "terminal_card" in r.data:
                    lines.append(r.data["terminal_card"])
                elif isinstance(r.data, dict) and "full_terminal_card" in r.data:
                    lines.append(r.data["full_terminal_card"])
                elif isinstance(r.data, dict) and "hud_card" in r.data:
                    lines.append(r.data["hud_card"])
            out_str = "\n".join(lines) if lines else resp_text
            ui_state.record_terminal_event(
                source=source,
                command=prompt,
                output=out_str,
                response=resp_text,
                tools=[{"tool": r.tool, "success": r.success, "message": r.message} for r in results],
            )
        except Exception:
            pass

        # If flight tracking tool was executed during interactive mode, transition into dynamic self-updating tracker
        has_flight_tool = any(a.tool in ("track_flight", "get_tracked_flight_info") for a in plan.actions)
        if interactive and has_flight_tool:
            from tools.flight import get_tracked_flight, run_dynamic_flight_tracker
            tracked = get_tracked_flight()
            if tracked and tracked.get("callsign"):
                time.sleep(1.2)
                run_dynamic_flight_tracker(tracked["callsign"])

        # If hardware monitor tool was executed with live mode during interactive mode, transition into dynamic live tracker
        has_live_hw = any(a.tool == "monitor_hardware" and a.args.get("live", False) for a in plan.actions)
        if interactive and has_live_hw:
            from tools.system import run_live_system_monitor
            time.sleep(1.0)
            run_live_system_monitor()

        # If ZimaOS monitor tool was executed with live mode during interactive mode, transition into dynamic live tracker
        has_live_zima = any(a.tool == "monitor_zimaos" and a.args.get("live", False) for a in plan.actions)
        if interactive and has_live_zima:
            from tools.zimaos import run_live_zimaos_monitor
            time.sleep(1.0)
            run_live_zimaos_monitor()
    except Exception as e:
        print(f"\n[!] Error during agent run: {e}")


def interactive_voice_loop(agent: OSAgent) -> None:
    """Continuous voice-controlled loop listening for 'GLaDOS' and executing commands."""
    from voice import VoiceListener, extract_wake_word_command, get_glados_quote, speak

    print_banner()
    check_llm_connection(agent)
    print("\n" + "=" * 65)
    print("   [+] APERTURE SCIENCE COMPUTER-AIDED ENRICHMENT CENTER")
    print(f"       Administrator : GLaDOS (Genetic Lifeform and Disk OS)")
    print(f"       Wake Word     : '{config.wake_word.upper()}' (e.g. 'GLaDOS...')")
    print("       Say 'exit', 'quit', or 'stop' to abort the test.")
    print("=" * 65 + "\n")

    boot_line = get_glados_quote("boot")
    speak(boot_line, wait=True)
    time.sleep(0.35)
    listener = VoiceListener()
    listener.calibrate_ambient_noise(duration=0.8)

    while True:
        try:
            try:
                from ui.state import ui_state
                ui_state.update(state="listening", text="Awaiting test subject auditory stimulus...")
            except Exception:
                pass

            print(f"\n[*] Listening for '{config.wake_word.title()}'...")

            def on_speech():
                try:
                    from ui.state import ui_state
                    ui_state.update(state="thinking", thought="Audio signal detected, processing...")
                except Exception:
                    pass
                print("  -> Audio signal detected, recording...", end="", flush=True)

            text = listener.listen_command(
                timeout=10.0,
                on_speech_detected=on_speech,
            )

            if not text:
                continue

            # Check if GLaDOS was explicitly called
            is_called, command = extract_wake_word_command(text, wake_word=config.wake_word)

            if not is_called and config.require_wake_word:
                # Ambient noise or conversation not directed to GLaDOS
                print(f" (Ignored: '{text}' - GLaDOS was not addressed)")
                continue

            # Use the remaining command or full text if wake word check was passed
            command_to_run = command if is_called else text
            print(f"\n[GLaDOS Addressed]: \"{text}\"")

            # Check for exit commands
            if any(w in text.lower() for w in ["exit", "quit", "goodbye", "stop voice", "shut down voice"]):
                print("Exiting GLaDOS voice testing protocol.")
                speak(get_glados_quote("shutdown"), wait=True)
                break

            # If the user just called her name with no command ("GLaDOS")
            if not command_to_run.strip():
                wake_prompt = get_glados_quote("wake_prompt")
                print(f"  -> GLaDOS: '{wake_prompt}'")
                speak(wake_prompt, wait=True)
                time.sleep(0.35)
                print("  -> Awaiting directive...")
                followup = listener.listen_command(timeout=8.0)
                if followup:
                    print(f"\n[Command]: \"{followup}\"")
                    command_to_run = followup
                else:
                    timeout_line = get_glados_quote("idle_timeout")
                    print(f"  -> GLaDOS: '{timeout_line}'")
                    speak(timeout_line, wait=True)
                    time.sleep(0.35)
                    continue

            execute_and_display(agent, command_to_run, source="voice")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting GLaDOS testing protocol.")
            speak(get_glados_quote("shutdown"), wait=True)
            break


def print_help_cli() -> None:
    """Displays command directory for the text-only CLI console."""
    print("""
+----------------------------------------------------------------------+
|           APERTURE SCIENCE CLI INTERFACE COMMAND DIRECTORY           |
+----------------------------------------------------------------------+
| Command               | Description                                  |
+-----------------------+----------------------------------------------+
| web / ui              | Launch GLaDOS ASCII console in browser       |
| voice on / off        | Turn microphone voice recognition on / off   |
| tts on / off          | Turn GLaDOS speech audio synthesis on / off  |
| flight                | Display telemetry HUD for tracked flight     |
| flight <callsign>     | Track live aircraft (e.g. flight AA100)      |
| hw / stats            | Query PC component usage, temps & power draw |
| ai stats              | Query GLaDOS AI RAM, tokens & generation rate|
| hw live / monitor     | Real-time self-updating component HUD monitor|
| zima / zimaos         | Query ZimaOS home server telemetry HUD       |
| zima live             | Real-time self-updating ZimaOS telemetry HUD |
| zima ip <address>     | Reconfigure destination IP of ZimaOS server  |
| zima login [user]     | Log in to ZimaOS to unlock CPU/RAM sensors    |
| zima token <token>    | Configure ZimaOS API Bearer token directly    |
| zima dash             | Open ZimaOS web dashboard in browser         |
| diag                  | Run system hardware and toolset diagnostic   |
| voice                 | Switch to voice listener mode                |
| help / ?              | Show this command directory                  |
| exit / quit / q       | Terminate terminal session                   |
+-----------------------+----------------------------------------------+
| Or enter any natural language prompt for GLaDOS to process.          |
+----------------------------------------------------------------------+
""")


def interactive_repl(agent: OSAgent) -> None:
    """Runs interactive command REPL loop."""
    print_banner()
    check_llm_connection(agent)
    if config.cli_mode:
        print("\n" + "=" * 65)
        print(" APERTURE SCIENCE COMPUTER-AIDED ENRICHMENT CENTER - CLI CONSOLE")
        print(" Text-Only Operational Mode Active (Audio Inhibited)")
        print(" Type 'help' for commands, 'flight' for radar telemetry, 'hw' for hardware.")
        print("=" * 65 + "\n")
    else:
        print("\nType your request or type 'voice' to speak. Type 'exit', 'quit', or 'diag'.\n")

    while True:
        try:
            prompt_str = "GLaDOS-CLI> " if config.cli_mode else "Agent> "
            user_input = input(prompt_str).strip()
            if not user_input:
                continue
            cmd_lower = user_input.lower()
            if cmd_lower in ("exit", "quit", "q"):
                print("Exiting Local OS Agent. Goodbye!")
                break
            if cmd_lower in ("help", "?", "commands"):
                print_help_cli()
                continue
            if cmd_lower in ("diag", "diagnostic", "test"):
                run_diagnostic()
                continue
            if cmd_lower in ("web", "ui", "webpage", "browser", "dashboard", "console"):
                from ui.server import start_ui_server
                start_ui_server(port=5000, open_browser=True)
                print("\n[+] Aperture Science GLaDOS Web Console launched at http://127.0.0.1:5000\n")
                continue
            if cmd_lower in ("voice on", "mic on", "listen on", "start listening"):
                from ui.server import start_voice_listener
                success, msg = start_voice_listener()
                print(f"\n[+] {msg}\n")
                continue
            if cmd_lower in ("voice off", "mic off", "listen off", "stop listening"):
                from ui.server import stop_voice_listener
                success, msg = stop_voice_listener()
                print(f"\n[+] {msg}\n")
                continue
            if cmd_lower in ("tts on", "glados voice on", "speech on", "unmute"):
                config.enable_tts = True
                try:
                    from ui.state import ui_state
                    ui_state.update(glados_voice=True)
                except Exception:
                    pass
                print("\n[+] GLaDOS voice audio output enabled.\n")
                continue
            if cmd_lower in ("tts off", "glados voice off", "speech off", "mute voice", "mute"):
                config.enable_tts = False
                try:
                    from ui.state import ui_state
                    ui_state.update(glados_voice=False)
                except Exception:
                    pass
                print("\n[+] GLaDOS voice audio output inhibited (muted).\n")
                continue
            if cmd_lower in ("voice", "listen", "mic"):
                if config.cli_mode:
                    print("[!] Voice mode disabled in pure CLI text-only mode.")
                else:
                    interactive_voice_loop(agent)
                continue
            if cmd_lower in ("flight", "tracked", "telemetry", "radar", "flight live", "radar live", "flight watch", "track live", "live flight", "live radar"):
                from tools.flight import run_dynamic_flight_tracker
                run_dynamic_flight_tracker()
                continue
            if cmd_lower.startswith("live track ") or cmd_lower.startswith("track ") or cmd_lower.startswith("flight "):
                parts = user_input.split(maxsplit=2 if cmd_lower.startswith("live track ") else 1)
                flight_arg = parts[-1].strip()
                if flight_arg:
                    from tools.flight import run_dynamic_flight_tracker
                    run_dynamic_flight_tracker(flight_arg)
                    continue
            if cmd_lower in ("hw live", "monitor", "monitor live", "stats live", "live monitor", "live hardware", "live hw"):
                from tools.system import run_live_system_monitor
                run_live_system_monitor()
                continue
            if cmd_lower in ("hw", "stats", "hardware", "components", "hw info", "ai stats", "glados stats", "tokens", "ai", "ai telemetry"):
                from tools.system import monitor_hardware
                _, telemetry = monitor_hardware(live=False)
                if isinstance(telemetry, dict) and "hud_card" in telemetry:
                    print(f"\n{telemetry['hud_card']}\n")
                else:
                    print(f"\n[Hardware Telemetry]:\n{telemetry}\n")
                continue
            if cmd_lower in ("server ssh", "zima ssh", "ssh", "open ssh", "ssh server"):
                from tools.zimaos import open_zimaos_ssh
                success, msg = open_zimaos_ssh()
                print(f"\n[+] {msg}\n" if success else f"\n[-] {msg}\n")
                continue
            if cmd_lower in ("zima live", "zimaos live", "zima monitor live", "live zima", "server live", "live server"):
                from tools.zimaos import run_live_zimaos_monitor
                run_live_zimaos_monitor()
                continue
            if cmd_lower.startswith("zima ip ") or cmd_lower.startswith("zimaos ip ") or cmd_lower.startswith("zima host ") or cmd_lower.startswith("server ip ") or cmd_lower.startswith("server host "):
                parts = user_input.split(maxsplit=2)
                new_ip = parts[-1].strip()
                from tools.zimaos import set_zimaos_host
                success, msg = set_zimaos_host(new_ip)
                print(f"\n[+] {msg}\n")
                continue
            if cmd_lower.startswith("zima launch ") or cmd_lower.startswith("zima open ") or cmd_lower.startswith("zima app ") or cmd_lower.startswith("server launch ") or cmd_lower.startswith("server open ") or cmd_lower.startswith("server app "):
                parts = user_input.split(maxsplit=2)
                target_app = parts[-1].strip()
                from tools.zimaos import launch_zimaos_app
                success, msg = launch_zimaos_app(target_app)
                print(f"\n[+] {msg}\n" if success else f"\n[-] {msg}\n")
                continue
            if cmd_lower in ("zima apps", "zimaos apps", "zima list", "zima containers", "server apps", "server list", "server containers"):
                from tools.zimaos import get_zimaos_apps_detailed
                apps = get_zimaos_apps_detailed()
                if apps:
                    print(f"\n+====================================================================+")
                    print(f"|        APERTURE SCIENCE REMOTE NODE - INSTALLED APPLICATIONS       |")
                    print(f"+====================================================================+")
                    for a in apps:
                        name_str = (a.get("name") or "Unknown")[:24]
                        state_str = (a.get("state") or "running")[:8]
                        url_str = a.get("url") or ""
                        print(f"  [{state_str:<7}] {name_str:<24} -> {url_str}")
                    print(f"+====================================================================+\n")
                else:
                    print("\n[-] No ZimaOS applications discovered.\n")
                continue
            if cmd_lower in ("zima", "zimaos", "zima status", "zima info", "zima hud", "server", "server status", "server info", "server hud"):
                from tools.zimaos import monitor_zimaos
                _, telemetry = monitor_zimaos(live=False)
                if isinstance(telemetry, dict) and "hud_card" in telemetry:
                    print(f"\n{telemetry['hud_card']}\n")
                else:
                    print(f"\n[ZimaOS Telemetry]:\n{telemetry}\n")
                continue

            if cmd_lower in ("clip", "clip that", "clip 30", "record that"):
                from tools.game_clipper import capture_game_clip
                res = capture_game_clip(30)
                if isinstance(res, dict) and "terminal_card" in res:
                    print(f"\n{res['terminal_card']}\n")
                if isinstance(res, dict) and "quip" in res:
                    print(f"[GLaDOS]: \"{res['quip']}\"\n")
                continue
            if cmd_lower in ("clips", "recent clips", "list clips"):
                from tools.game_clipper import list_recent_clips
                res = list_recent_clips()
                if isinstance(res, dict) and "terminal_card" in res:
                    print(f"\n{res['terminal_card']}\n")
                continue
            if cmd_lower in ("wellness", "subject", "subject status", "health", "biometrics"):
                from tools.subject_wellness import check_subject_status
                res = check_subject_status()
                if isinstance(res, dict) and "terminal_card" in res:
                    print(f"\n{res['terminal_card']}\n")
                continue
            if cmd_lower in ("water", "log water", "drink water"):
                from tools.subject_wellness import log_water_intake
                res = log_water_intake()
                print(f"\n[GLaDOS]: \"{res.get('message')}\"\n")
                continue
            if cmd_lower in ("lemons", "combustible lemons"):
                from tools.soundboard import play_soundboard
                res = play_soundboard("lemons")
                if isinstance(res, dict) and "terminal_card" in res:
                    print(f"\n{res['terminal_card']}\n")
                continue
            if cmd_lower in ("jellyfin", "media status", "now playing"):
                from tools.jellyfin import get_jellyfin_now_playing
                res = get_jellyfin_now_playing()
                if isinstance(res, dict) and "terminal_card" in res:
                    print(f"\n{res['terminal_card']}\n")
                continue


            execute_and_display(agent, user_input, interactive=True)
            print("-" * 50)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Local OS Agent. Goodbye!")
            break


def preview_all_voices() -> None:
    """Plays a preview of all available voices so the user can select their favorite."""
    from voice.tts import VOICE_PRESETS, TextToSpeech
    print("\n--- Auditioning Available Cortana Voices ---")
    for key, (voice_id, desc) in VOICE_PRESETS.items():
        print(f"\n[*] Voice Preset: '{key}' ({voice_id})")
        print(f"    Description : {desc}")
        print(f"    Speaking sample now...")
        engine = TextToSpeech(voice=voice_id)
        phrase = f"Hello. I am Cortana, using the {key} voice profile. How do I sound to you?"
        engine.speak(phrase, wait=True)
    print("\n--- Finished Auditioning Voices ---")
    print("Tip: You can select any voice permanently by launching with: --voice-name <name>")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local OS Agent CLI")
    parser.add_argument("--prompt", "-p", type=str, help="Single prompt execution mode")
    parser.add_argument("--base-url", type=str, default=config.llm_base_url, help="LLM base URL")
    parser.add_argument("--model", "-m", type=str, default=config.llm_model, help="LLM model name")
    parser.add_argument("--cli", "--text-only", action="store_true", dest="cli_mode", help="Launch in pure text-only CLI mode without voice or automated browser popups")
    parser.add_argument("--voice", "-v", action="store_true", help="Launch directly in voice interaction mode")
    parser.add_argument("--ui", "--web", action="store_true", dest="ui", help="Launch GLaDOS ASCII console in browser")
    parser.add_argument("--voice-name", type=str, default=None, help="TTS Voice preset or full name (libby, aria, ava, maisie)")
    parser.add_argument("--preview-voices", action="store_true", help="Audition all available voice presets out loud")
    parser.add_argument("--no-tts", action="store_true", help="Disable voice speech feedback")
    parser.add_argument("--test-tools", action="store_true", help="Run local tool diagnostics")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("query", nargs="*", help="Optional direct prompt to execute")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.cli_mode:
        config.cli_mode = True
        config.enable_tts = False
        args.no_tts = True

    if args.preview_voices:
        preview_all_voices()
        return

    if args.voice_name:
        from voice.tts import VOICE_PRESETS, tts_engine
        selected = VOICE_PRESETS.get(args.voice_name.lower(), (args.voice_name, ""))[0]
        config.tts_voice = selected
        tts_engine.voice = selected

    if args.test_tools:
        run_diagnostic()
        return

    prompt = args.prompt or (" ".join(args.query).strip() if args.query else None)

    # Launch standalone web console if requested via 'web'/'ui' or --web/--ui flag
    if (prompt and prompt.lower() in ("web", "ui", "console", "dashboard")) or (args.ui and not prompt):
        from ui.server import start_ui_server
        print("[*] Starting Aperture Science GLaDOS Web Console at http://127.0.0.1:5000...")
        start_ui_server(port=5000, open_browser=True)
        print("[+] Web console active in browser. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\nShutting down GLaDOS Web Console.")
            return

    # If --ui flag with prompt, start UI server in background
    if args.ui:
        from ui.server import start_ui_server
        start_ui_server(port=5000, open_browser=True)

    # Enforce single-instance execution for voice and interactive modes (unless pure text CLI mode)
    if not args.cli_mode and (args.voice or not prompt) and not acquire_single_instance_lock():
        sys.exit(0)

    enable_voice = not args.no_tts and not args.cli_mode
    agent = OSAgent(base_url=args.base_url, model=args.model, enable_voice=enable_voice)

    # Initialize real-time flight auto-updater if a flight is currently tracked
    try:
        from tools.flight import get_tracked_flight, ensure_flight_auto_updater
        if get_tracked_flight():
            ensure_flight_auto_updater()
    except Exception:
        pass

    # Ensure OBS Studio Replay Buffer is primed in background for instant clipping
    try:
        import threading
        from tools.game_clipper import ensure_obs_replay_buffer
        threading.Thread(target=ensure_obs_replay_buffer, daemon=True).start()
    except Exception:
        pass

    if args.voice and not args.cli_mode:
        interactive_voice_loop(agent)
    elif prompt:
        is_live = any(w in prompt.lower() for w in ("live track", "flight live", "radar live", "track live", "live tracker", "monitor live", "hw live", "live hardware", "zima live", "zimaos live"))
        execute_and_display(agent, prompt, interactive=is_live)
    else:
        interactive_repl(agent)


if __name__ == "__main__":
    main()
