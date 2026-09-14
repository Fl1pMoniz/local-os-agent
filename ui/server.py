"""Lightweight Web UI server for GLaDOS with real-time SSE telemetry."""

import json
import logging
import os
import queue
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config import config
from ui.state import ui_state

logger = logging.getLogger("local_os_agent.ui.server")
UI_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", "5000"))

_voice_thread = None
_voice_thread_running = False


def start_voice_listener() -> tuple[bool, str]:
    """Starts local microphone voice recognition loop in a daemon thread."""
    global _voice_thread, _voice_thread_running
    if _voice_thread_running:
        return True, "Voice recognition is already active."
    _voice_thread_running = True
    config.voice_recognition_enabled = True
    ui_state.update(voice_recognition=True)

    def _loop():
        try:
            from agent import OSAgent
            from voice import VoiceListener, extract_wake_word_command, speak

            agent = OSAgent()
            listener = VoiceListener()
            listener.calibrate_ambient_noise(duration=0.5)
            while _voice_thread_running:
                ui_state.update(state="listening")
                text = listener.listen_command(timeout=8.0)
                if not text or not _voice_thread_running:
                    continue
                is_called, cmd = extract_wake_word_command(text)
                if is_called or not config.require_wake_word:
                    cmd_to_run = cmd if is_called and cmd else text
                    try:
                        from voice.audio_arbiter import stop_all_audio

                        stop_all_audio()
                    except Exception:
                        pass
                    ui_state.update(
                        state="thinking", thought=f"Audio command received: {cmd_to_run}"
                    )
                    plan, results = agent.run(cmd_to_run)
                    resp_text = plan.response or plan.thought or "Directive executed."

                    lines = []
                    if resp_text:
                        lines.append(f'[GLaDOS]: "{resp_text}"')
                    for r in results:
                        icon = "+" if r.success else "x"
                        lines.append(f"  [{icon}] {r.tool}: {r.message}")
                        if isinstance(r.data, dict) and "full_terminal_card" in r.data:
                            lines.append(r.data["full_terminal_card"])
                        elif isinstance(r.data, dict) and "hud_card" in r.data:
                            lines.append(r.data["hud_card"])

                    output_str = "\n".join(lines) if lines else resp_text

                    # Broadcast terminal execution event to glados-web terminal
                    ui_state.record_terminal_event(
                        source="voice",
                        command=cmd_to_run,
                        output=output_str,
                        response=resp_text,
                        tools=[
                            {"tool": r.tool, "success": r.success, "message": r.message}
                            for r in results
                        ],
                    )

                    # Update telemetry cards in web UI if query was sensor/radar related
                    cmd_lower = cmd_to_run.lower()
                    if any(w in cmd_lower for w in ("hardware", "hw", "pc", "temp", "component")):
                        from tools.system import get_hardware_telemetry

                        ui_state.update(
                            hardware_telemetry=get_hardware_telemetry(), active_telemetry_tab="pc"
                        )
                    elif any(w in cmd_lower for w in ("zima", "zimaos", "server")):
                        from tools.zimaos import get_zimaos_telemetry

                        ui_state.update(
                            zimaos_telemetry=get_zimaos_telemetry(), active_telemetry_tab="zimaos"
                        )
                    elif any(w in cmd_lower for w in ("flight", "radar", "track")):
                        from tools.flight import get_tracked_flight

                        ui_state.update(tracked_flight=get_tracked_flight())

                    has_audio_tool = any(
                        r.tool in ("play_soundboard", "sing_song", "play_portal_sfx")
                        for r in results
                    )
                    if plan.response and config.enable_tts and not has_audio_tool:
                        ui_state.update(state="speaking", text=plan.response)
                        speak(plan.response, wait=True)
                    else:
                        ui_state.update(state="idle")
                time.sleep(0.2)
        except Exception as e:
            logger.debug(f"Voice listener thread exception: {e}")
        finally:
            ui_state.update(state="idle", voice_recognition=False)

    _voice_thread = threading.Thread(target=_loop, daemon=True)
    _voice_thread.start()
    return True, "Voice recognition activated."


def stop_voice_listener() -> tuple[bool, str]:
    """Stops the local microphone voice recognition loop."""
    global _voice_thread_running
    _voice_thread_running = False
    config.voice_recognition_enabled = False
    ui_state.update(voice_recognition=False, state="idle")
    return True, "Voice recognition deactivated."


class GLaDOSRequestHandler(SimpleHTTPRequestHandler):
    """Handles HTTP requests, API commands, and SSE real-time state streams."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(f"{self.client_address[0]} - {format % args}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html_file = UI_DIR / "index.html"
            with open(html_file, "rb") as f:
                self.wfile.write(f.read())
            return

        elif parsed.path.startswith("/assets/"):
            asset_name = parsed.path[len("/assets/") :]
            asset_file = UI_DIR / "assets" / asset_name
            if asset_file.exists() and asset_file.is_file():
                ext = asset_file.suffix.lower()
                content_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                    ".glb": "model/gltf-binary",
                    ".gltf": "model/gltf+json",
                    ".bin": "application/octet-stream",
                    ".wasm": "application/wasm",
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".woff": "font/woff",
                    ".woff2": "font/woff2",
                    ".ttf": "font/ttf",
                    ".otf": "font/otf",
                }
                c_type = content_types.get(ext, "application/octet-stream")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", c_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(asset_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
            return

        elif parsed.path.startswith("/fonts/"):
            font_name = parsed.path[len("/fonts/") :]
            font_file = UI_DIR / "fonts" / font_name
            if font_file.exists() and font_file.is_file():
                ext = font_file.suffix.lower()
                font_content_types = {
                    ".woff": "font/woff",
                    ".woff2": "font/woff2",
                    ".ttf": "font/ttf",
                    ".otf": "font/otf",
                    ".eot": "application/vnd.ms-fontobject",
                }
                c_type = font_content_types.get(ext, "application/octet-stream")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", c_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(font_file, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
            return

        elif parsed.path == "/api/state":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            state_data = ui_state.get_state()
            self.wfile.write(json.dumps(state_data).encode("utf-8"))
            return

        elif parsed.path == "/api/telemetry":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from tools.flight import get_tracked_flight
                from tools.system import get_hardware_telemetry
                from tools.zimaos import get_zimaos_telemetry

                hw = get_hardware_telemetry()
                zima = get_zimaos_telemetry()
                flight = get_tracked_flight()
                ui_state.update(hardware_telemetry=hw, zimaos_telemetry=zima, tracked_flight=flight)
                payload = {
                    "success": True,
                    "hardware": hw,
                    "zimaos": zima,
                    "flight": flight,
                    "active_tab": ui_state.active_telemetry_tab,
                    "voice_recognition": ui_state.voice_recognition,
                    "glados_voice": config.enable_tts,
                    "terminal_events": list(ui_state.terminal_events),
                }
            except Exception as e:
                payload = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        elif parsed.path == "/api/voice_control":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "voice_recognition": ui_state.voice_recognition,
                        "glados_voice": config.enable_tts,
                    }
                ).encode("utf-8")
            )
            return

        elif parsed.path == "/api/events":
            # Server-Sent Events stream
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Send initial state
            init_json = json.dumps(ui_state.get_state())
            self.wfile.write(f"data: {init_json}\n\n".encode())
            self.wfile.flush()

            sub_queue = ui_state.subscribe()
            try:
                while True:
                    try:
                        data = sub_queue.get(timeout=20.0)
                        msg = f"data: {json.dumps(data)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Keep-alive comment
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                ui_state.unsubscribe(sub_queue)
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/voice_control":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                payload = json.loads(body) if body else {}
                if "voice_recognition" in payload:
                    vr_val = bool(payload["voice_recognition"])
                    if vr_val:
                        start_voice_listener()
                    else:
                        stop_voice_listener()
                if "glados_voice" in payload:
                    gv_val = bool(payload["glados_voice"])
                    config.enable_tts = gv_val
                    ui_state.update(glados_voice=gv_val)

                resp = {
                    "success": True,
                    "voice_recognition": ui_state.voice_recognition,
                    "glados_voice": config.enable_tts,
                }
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        if parsed.path == "/api/action":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                payload = json.loads(body)
                action = payload.get("action", "").lower()

                response_data = {"success": True, "message": "OK"}

                if action in ("toggle_voice_recognition", "toggle_voice"):
                    if ui_state.voice_recognition:
                        stop_voice_listener()
                    else:
                        start_voice_listener()
                    response_data = {
                        "success": True,
                        "voice_recognition": ui_state.voice_recognition,
                        "message": f"Voice recognition {'activated' if ui_state.voice_recognition else 'deactivated'}.",
                    }

                elif action in ("toggle_tts", "toggle_glados_voice"):
                    config.enable_tts = not config.enable_tts
                    ui_state.update(glados_voice=config.enable_tts)
                    response_data = {
                        "success": True,
                        "glados_voice": config.enable_tts,
                        "message": f"GLaDOS speech audio output {'enabled' if config.enable_tts else 'inhibited'}.",
                    }

                elif action == "set_active_telemetry_tab":
                    tab = payload.get("tab", "pc").lower()
                    if tab not in ("pc", "zimaos"):
                        tab = "pc"
                    ui_state.update(active_telemetry_tab=tab)
                    response_data = {"success": True, "active_tab": tab}

                elif action == "get_telemetry":
                    from tools.flight import get_tracked_flight
                    from tools.system import get_hardware_telemetry
                    from tools.zimaos import get_zimaos_telemetry

                    hw = get_hardware_telemetry()
                    zima = get_zimaos_telemetry()
                    flight = get_tracked_flight()
                    ui_state.update(
                        hardware_telemetry=hw, zimaos_telemetry=zima, tracked_flight=flight
                    )
                    response_data = {
                        "success": True,
                        "hardware": hw,
                        "zimaos": zima,
                        "flight": flight,
                        "active_tab": ui_state.active_telemetry_tab,
                        "voice_recognition": ui_state.voice_recognition,
                        "glados_voice": config.enable_tts,
                    }

                elif action == "sing":
                    song_name = payload.get("song", "still_alive")
                    from tools.songs import sing_song

                    success, msg = sing_song(song_name)
                    response_data = {"success": success, "message": msg}

                elif action == "stop_song":
                    from tools.songs import stop_song

                    success, msg = stop_song()
                    response_data = {"success": success, "message": msg}

                elif action == "speak":
                    text = payload.get("text", "")
                    if text:
                        from voice import speak

                        speak(text)
                    response_data = {"success": True, "message": "Speaking initiated."}

                elif action == "quip":
                    from voice import get_glados_quote, speak

                    quip = get_glados_quote("greetings")
                    speak(quip)
                    response_data = {"success": True, "message": quip}

                elif action == "roast":
                    from tools.companion import roast_user
                    from voice import speak

                    success, msg = roast_user()
                    speak(msg)
                    response_data = {"success": success, "message": msg}

                elif action == "radio":
                    from tools.sfx import play_portal_sfx

                    success, msg = play_portal_sfx("radio")
                    response_data = {"success": success, "message": msg}

                elif action == "turret":
                    from tools.sfx import play_portal_sfx

                    success, msg = play_portal_sfx("turret_hello")
                    response_data = {"success": success, "message": msg}

                elif action == "stop_sfx":
                    from tools.sfx import stop_sfx

                    success, msg = stop_sfx()
                    response_data = {"success": success, "message": msg}

                elif action == "weather":
                    from tools.web import get_weather
                    from voice import speak

                    success, msg = get_weather()
                    speak(msg)
                    response_data = {"success": success, "message": msg}

                elif action == "track_flight":
                    from tools.flight import track_flight

                    flight_q = payload.get("flight", "AA100")
                    open_b = payload.get("open_browser", False)
                    success, msg = track_flight(flight_q, open_browser=open_b)
                    response_data = {"success": success, "message": msg}

                elif action == "zimaos_status":
                    from tools.zimaos import get_zimaos_status

                    success, msg = get_zimaos_status()
                    response_data = {"success": success, "message": msg}

                elif action == "zimaos_apps":
                    from tools.zimaos import get_zimaos_apps_detailed, list_zimaos_apps

                    detailed = payload.get("detailed", False)
                    if detailed:
                        apps_list = get_zimaos_apps_detailed()
                        response_data = {"success": True, "apps": apps_list}
                    else:
                        success, msg = list_zimaos_apps()
                        response_data = {"success": success, "message": msg}

                elif action == "launch_zimaos_app":
                    from tools.zimaos import launch_zimaos_app

                    app_name = payload.get("app") or payload.get("app_name") or ""
                    success, msg = launch_zimaos_app(app_name)
                    response_data = {"success": success, "message": msg}

                elif action == "zimaos_dashboard":
                    from tools.zimaos import open_zimaos_dashboard

                    success, msg = open_zimaos_dashboard()
                    response_data = {"success": success, "message": msg}

                elif action in (
                    "open_zimaos_ssh",
                    "launch_zimaos_ssh",
                    "zimaos_ssh",
                    "server_ssh",
                    "ssh",
                ):
                    from tools.zimaos import open_zimaos_ssh

                    user = payload.get("user") or payload.get("ssh_user")
                    port = payload.get("port")
                    success, msg = open_zimaos_ssh(ssh_user=user, port=port)
                    response_data = {"success": success, "message": msg}

                elif action == "add_zima_app":
                    from tools.zimaos import add_custom_zima_app

                    name = payload.get("name", "")
                    url = payload.get("url", "")
                    cat = payload.get("category", "General")
                    success, msg = add_custom_zima_app(name, url, cat)
                    response_data = {"success": success, "message": msg}

                elif action == "delete_zima_app":
                    from tools.zimaos import delete_custom_zima_app

                    name = payload.get("name", "") or payload.get("id", "")
                    success, msg = delete_custom_zima_app(name)
                    response_data = {"success": success, "message": msg}

                elif action == "get_custom_zima_apps":
                    from tools.zimaos import get_custom_zima_apps

                    apps = get_custom_zima_apps()
                    response_data = {"success": True, "apps": apps}

                elif action == "get_zima_host":
                    from tools.zimaos import get_zimaos_host

                    host = get_zimaos_host()
                    response_data = {"success": True, "host": host}

                elif action == "set_zima_host":
                    from tools.zimaos import set_zimaos_host

                    new_host = payload.get("host", "")
                    success, msg = set_zimaos_host(new_host)
                    response_data = {
                        "success": success,
                        "message": msg,
                        "host": payload.get("host", ""),
                    }

                elif action in ("clip_that", "clip", "capture_clip"):
                    from tools.game_clipper import capture_game_clip

                    secs = int(payload.get("seconds", 30))
                    res = capture_game_clip(seconds=secs)
                    response_data = {
                        "success": res.get("success", False),
                        "clip": res,
                        "message": res.get("message", "Clip saved."),
                    }

                elif action in ("list_clips", "clips"):
                    from tools.game_clipper import list_recent_clips

                    res = list_recent_clips()
                    response_data = {"success": True, "clips": res}

                elif action == "soundboard":
                    from tools.soundboard import play_soundboard

                    clip_q = payload.get("clip") or payload.get("name") or "lemons"
                    res = play_soundboard(clip_q)
                    response_data = res

                elif action in ("wellness", "subject_status"):
                    from tools.subject_wellness import check_subject_status

                    res = check_subject_status()
                    response_data = res

                elif action in ("water", "log_water"):
                    from tools.subject_wellness import log_water_intake

                    ml = int(payload.get("ml", 250))
                    res = log_water_intake(ml)
                    response_data = res

                elif action in ("analyze_screen", "look", "inspect"):
                    from tools.vision import analyze_screen

                    prompt_txt = payload.get("prompt", "Inspect screen")
                    res = analyze_screen(prompt_txt)
                    response_data = res

                elif action == "get_tracked_flight":
                    from tools.flight import ensure_flight_auto_updater, get_tracked_flight

                    f_data = get_tracked_flight()
                    if f_data:
                        ensure_flight_auto_updater()
                    response_data = {"success": bool(f_data), "flight": f_data}

                elif action == "volume_relative":
                    from tools.audio import change_volume_relative

                    try:
                        delta = int(float(str(payload.get("delta", 10)).replace("%", "").strip()))
                    except (ValueError, TypeError):
                        delta = 10
                    success, msg = change_volume_relative(delta)
                    response_data = {"success": success, "message": msg}

                elif action == "volume_set":
                    from tools.audio import set_volume

                    try:
                        level = int(float(str(payload.get("level", 50)).replace("%", "").strip()))
                    except (ValueError, TypeError):
                        level = 50
                    success, msg = set_volume(level)
                    response_data = {"success": success, "message": msg}

                elif action == "youtube":
                    from tools.media import play_youtube

                    query = payload.get("query", "")
                    music = payload.get("music", False)
                    success, msg = play_youtube(query, music=music)
                    response_data = {"success": success, "message": msg}

                elif action == "prompt":
                    user_prompt = payload.get("prompt", "").strip()
                    if user_prompt:
                        p_lower = user_prompt.lower()
                        if p_lower in (
                            "hw",
                            "stats",
                            "hardware",
                            "components",
                            "hw live",
                            "monitor",
                            "monitor live",
                            "ai stats",
                            "glados stats",
                            "ai",
                            "tokens",
                            "ai telemetry",
                        ):
                            from tools.system import get_hardware_telemetry

                            hw = get_hardware_telemetry()
                            card = hw.get("full_terminal_card") or hw.get("hud_card", "")
                            ui_state.update(hardware_telemetry=hw, active_telemetry_tab="pc")
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": card,
                                "message": "Host hardware telemetry synchronized.",
                                "telemetry": {"hardware": hw, "active_tab": "pc"},
                            }
                        elif p_lower in ("server ssh", "zima ssh", "ssh", "open ssh", "ssh server"):
                            from tools.zimaos import open_zimaos_ssh

                            success, msg = open_zimaos_ssh()
                            response_data = {
                                "success": success,
                                "command": user_prompt,
                                "output": f"[+] {msg}" if success else f"[-] {msg}",
                                "message": msg,
                                "glados_voice": config.enable_tts,
                                "voice_recognition": ui_state.voice_recognition,
                            }
                        elif p_lower in (
                            "zima",
                            "zimaos",
                            "zima live",
                            "zima status",
                            "zima hud",
                            "server",
                            "server status",
                            "server hud",
                            "server info",
                        ):
                            from tools.zimaos import get_zimaos_telemetry

                            zima = get_zimaos_telemetry()
                            card = zima.get("full_terminal_card") or zima.get("hud_card", "")
                            ui_state.update(zimaos_telemetry=zima, active_telemetry_tab="zimaos")
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": card,
                                "message": "ZimaOS remote telemetry synchronized.",
                                "telemetry": {"zimaos": zima, "active_tab": "zimaos"},
                            }
                        elif (
                            p_lower.startswith("zima ip ")
                            or p_lower.startswith("zima host ")
                            or p_lower.startswith("server ip ")
                            or p_lower.startswith("server host ")
                        ):
                            new_host = user_prompt.split(maxsplit=2)[-1].strip()
                            from tools.zimaos import get_zimaos_telemetry, set_zimaos_host

                            success, msg = set_zimaos_host(new_host)
                            zima = get_zimaos_telemetry()
                            ui_state.update(zimaos_telemetry=zima)
                            response_data = {
                                "success": success,
                                "command": user_prompt,
                                "output": msg,
                                "message": msg,
                                "telemetry": {"zimaos": zima},
                            }
                        elif (
                            p_lower.startswith("flight ")
                            or p_lower.startswith("track ")
                            or p_lower in ("flight", "radar", "tracked")
                        ):
                            parts = user_prompt.split(maxsplit=1)
                            callsign = parts[1].strip() if len(parts) > 1 else ""
                            if callsign:
                                from tools.flight import get_tracked_flight, track_flight

                                success, msg = track_flight(callsign, open_browser=False)
                                flight = get_tracked_flight()
                            else:
                                from tools.flight import get_tracked_flight

                                flight = get_tracked_flight()
                                msg = (
                                    "Active radar lock retrieved."
                                    if flight
                                    else "No flight currently tracked."
                                )
                            card = (
                                (flight.get("full_terminal_card") or flight.get("hud_card", ""))
                                if flight
                                else msg
                            )
                            ui_state.update(tracked_flight=flight)
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": card,
                                "message": msg,
                                "telemetry": {"flight": flight},
                            }
                        elif p_lower in ("clip", "clip that", "clip 30", "record that"):
                            from tools.game_clipper import capture_game_clip

                            res = capture_game_clip(30)
                            card = res.get("terminal_card", "")
                            quip = res.get("quip", "")
                            output_text = (
                                f'{card}\n[GLaDOS]: "{quip}"'
                                if card
                                else f"[+] {res.get('message')}"
                            )
                            response_data = {
                                "success": bool(res.get("success", False)),
                                "command": user_prompt,
                                "output": output_text,
                                "message": res.get("message", "Clip saved."),
                            }
                        elif p_lower in ("clips", "recent clips", "list clips"):
                            from tools.game_clipper import list_recent_clips

                            res = list_recent_clips()
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": res.get("terminal_card", ""),
                                "message": "Archived highlights retrieved.",
                            }
                        elif p_lower in ("wellness", "subject", "subject status", "biometrics"):
                            from tools.subject_wellness import check_subject_status

                            res = check_subject_status()
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": res.get("terminal_card", ""),
                                "message": res.get("message", ""),
                            }
                        elif p_lower in ("water", "log water", "drink water"):
                            from tools.subject_wellness import log_water_intake

                            res = log_water_intake()
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": f'[GLaDOS]: "{res.get("message")}"',
                                "message": res.get("message", ""),
                            }
                        elif p_lower in (
                            "lemons",
                            "combustible lemons",
                            "play lemons",
                            "play cave johnson voiceline",
                            "cave johnson voiceline",
                            "soundboard lemons",
                        ):
                            from tools.soundboard import play_soundboard

                            res = play_soundboard("lemons")
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": res.get("terminal_card", ""),
                                "message": res.get("message", ""),
                            }
                        elif p_lower in ("jellyfin", "media status", "now playing"):
                            from tools.jellyfin import get_jellyfin_now_playing

                            res = get_jellyfin_now_playing()
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": res.get("terminal_card", ""),
                                "message": res.get("message", ""),
                            }
                        elif p_lower in ("voice on", "mic on", "listen on", "start listening"):
                            success, msg = start_voice_listener()
                            response_data = {
                                "success": success,
                                "command": user_prompt,
                                "output": f"[+] {msg}",
                                "message": msg,
                                "voice_recognition": True,
                            }
                        elif p_lower in ("voice off", "mic off", "listen off", "stop listening"):
                            success, msg = stop_voice_listener()
                            response_data = {
                                "success": success,
                                "command": user_prompt,
                                "output": f"[+] {msg}",
                                "message": msg,
                                "voice_recognition": False,
                            }
                        elif p_lower in ("tts on", "glados voice on", "speech on", "unmute"):
                            config.enable_tts = True
                            ui_state.update(glados_voice=True)
                            msg = "GLaDOS acoustic speech synthesis enabled."
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": f"[+] {msg}",
                                "message": msg,
                                "glados_voice": True,
                            }
                        elif p_lower in (
                            "tts off",
                            "glados voice off",
                            "speech off",
                            "mute voice",
                            "mute",
                        ):
                            config.enable_tts = False
                            ui_state.update(glados_voice=False)
                            msg = "GLaDOS acoustic speech synthesis inhibited (muted)."
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": f"[+] {msg}",
                                "message": msg,
                                "glados_voice": False,
                            }
                        elif p_lower in ("help", "?", "commands"):
                            help_msg = (
                                "+--------------------------------------------------------------------+\n"
                                "|           APERTURE SCIENCE CLI INTERFACE COMMAND DIRECTORY         |\n"
                                "+--------------------------------------------------------------------+\n"
                                "| hw / stats            : Display PC component & thermal HUD         |\n"
                                "| zima / zimaos         : Display ZimaOS server telemetry HUD        |\n"
                                "| flight <callsign>     : Track live aircraft (e.g. flight AA100)    |\n"
                                "| voice on / off        : Turn microphone voice recognition on / off |\n"
                                "| tts on / off          : Turn GLaDOS speech synthesis on / off      |\n"
                                "| roast me              : GLaDOS analyzes and insults test subject   |\n"
                                "| quip                  : Random GLaDOS test chamber quip            |\n"
                                "| still alive           : Sing Still Alive acoustic simulation       |\n"
                                "| radio / turret        : Play Portal radio loop / Turret audio feed |\n"
                                "| stop audio            : Terminate all active music & sound loops   |\n"
                                "| lock pc               : Lock workstation console                   |\n"
                                "| cls / clear           : Clear terminal console screen              |\n"
                                "+--------------------------------------------------------------------+"
                            )
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": help_msg,
                                "message": "Command directory displayed.",
                            }
                        elif p_lower in ("cls", "clear"):
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": "",
                                "clear": True,
                            }
                        else:
                            try:
                                from voice.audio_arbiter import stop_all_audio

                                stop_all_audio()
                            except Exception:
                                pass
                            ui_state.update(state="thinking", thought=f"Executing: {user_prompt}")
                            from agent import OSAgent

                            agent = OSAgent()
                            plan, results = agent.run(user_prompt)
                            resp_text = plan.response or plan.thought or "Directive executed."
                            has_audio_tool = any(
                                r.tool in ("play_soundboard", "sing_song", "play_portal_sfx")
                                for r in results
                            )
                            ui_state.update(
                                state="speaking"
                                if (config.enable_tts and not has_audio_tool)
                                else "idle",
                                text=resp_text,
                            )
                            if config.enable_tts and plan.response and not has_audio_tool:
                                from voice import speak

                                speak(plan.response)
                            lines = []
                            if resp_text:
                                lines.append(f'[GLaDOS]: "{resp_text}"')
                            for r in results:
                                icon = "+" if r.success else "x"
                                lines.append(f"  [{icon}] {r.tool}: {r.message}")
                                if isinstance(r.data, dict) and "full_terminal_card" in r.data:
                                    lines.append(r.data["full_terminal_card"])
                                elif isinstance(r.data, dict) and "hud_card" in r.data:
                                    lines.append(r.data["hud_card"])
                            output_str = "\n".join(lines) if lines else resp_text
                            response_data = {
                                "success": True,
                                "command": user_prompt,
                                "output": output_str,
                                "message": resp_text,
                                "response": resp_text,
                                "glados_voice": config.enable_tts,
                                "voice_recognition": ui_state.voice_recognition,
                            }

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
            except Exception as e:
                logger.exception("Error processing API action: %s", e)
                if action == "prompt":
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    err_resp = {
                        "success": False,
                        "command": payload.get("prompt", "") if isinstance(payload, dict) else "",
                        "output": f"[!] Error executing directive: {e}",
                        "message": f"Execution error: {e}",
                        "response": f"Execution error: {e}",
                        "error": str(e),
                    }
                    self.wfile.write(json.dumps(err_resp).encode("utf-8"))
                else:
                    self.send_response(HTTPStatus.BAD_REQUEST)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def start_ui_server(
    port: int = PORT, open_browser: bool = False, host: str | None = None
) -> ThreadingHTTPServer:
    """Starts the GLaDOS UI server in a daemon background thread."""
    bind_host = (
        host
        or os.getenv("UI_HOST")
        or ("0.0.0.0" if os.getenv("CONTAINER_MODE") == "true" else "127.0.0.1")
    )
    server = ThreadingHTTPServer((bind_host, port), GLaDOSRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    url = f"http://{display_host}:{port}"
    logger.info(f"GLaDOS Visual UI active at {url} (bound to {bind_host}:{port})")

    # Synchronize any existing flight tracking into ui_state and start auto-updater
    try:
        from tools.flight import ensure_flight_auto_updater, get_tracked_flight

        active_flight = get_tracked_flight()
        if active_flight:
            ui_state.update(tracked_flight=active_flight)
            ensure_flight_auto_updater()
    except Exception:
        pass

    # Start background telemetry poller (hardware and zimaos)
    def _telemetry_polling_loop():
        time.sleep(0.5)
        while True:
            try:
                from tools.system import get_hardware_telemetry
                from tools.zimaos import get_zimaos_telemetry

                hw = get_hardware_telemetry()
                zima = get_zimaos_telemetry()
                ui_state.update(hardware_telemetry=hw, zimaos_telemetry=zima)
            except Exception as ex:
                logger.debug(f"Telemetry background poller exception: {ex}")
            time.sleep(2.5)

    _tel_thread = threading.Thread(target=_telemetry_polling_loop, daemon=True)
    _tel_thread.start()

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    return server


def run_ui_app() -> None:
    """Blocking runner for the GLaDOS Web UI, ideal for container or foreground server execution."""
    bind_host = os.getenv("UI_HOST") or (
        "0.0.0.0" if os.getenv("CONTAINER_MODE") == "true" else "127.0.0.1"
    )
    port = int(os.getenv("UI_PORT") or os.getenv("PORT") or PORT)
    headless = os.getenv("HEADLESS", "false").lower() in ("true", "1", "yes")

    server = start_ui_server(port=port, open_browser=not headless, host=bind_host)
    print(f"Aperture Science GLaDOS UI running on http://{bind_host}:{port} (Headless: {headless})")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down UI server gracefully.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run_ui_app()
