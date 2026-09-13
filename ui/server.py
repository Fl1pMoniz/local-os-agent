"""Lightweight Web UI server for GLaDOS with real-time SSE telemetry."""

import json
import logging
import os
import queue
import threading
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ui.state import ui_state

logger = logging.getLogger("local_os_agent.ui.server")
UI_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", "5000"))


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
            asset_name = parsed.path[len("/assets/"):]
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

        elif parsed.path == "/api/state":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            state_data = ui_state.get_state()
            self.wfile.write(json.dumps(state_data).encode("utf-8"))
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
            self.wfile.write(f"data: {init_json}\n\n".encode("utf-8"))
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

        if parsed.path == "/api/action":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                payload = json.loads(body)
                action = payload.get("action", "").lower()

                response_data = {"success": True, "message": "OK"}

                if action == "sing":
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
                    from tools.zimaos import list_zimaos_apps
                    success, msg = list_zimaos_apps()
                    response_data = {"success": success, "message": msg}

                elif action == "zimaos_dashboard":
                    from tools.zimaos import open_zimaos_dashboard
                    success, msg = open_zimaos_dashboard()
                    response_data = {"success": success, "message": msg}

                elif action == "volume_relative":
                    from tools.audio import change_volume_relative
                    delta = int(payload.get("delta", 10))
                    success, msg = change_volume_relative(delta)
                    response_data = {"success": success, "message": msg}

                elif action == "volume_set":
                    from tools.audio import set_volume
                    level = int(payload.get("level", 50))
                    success, msg = set_volume(level)
                    response_data = {"success": success, "message": msg}

                elif action == "youtube":
                    from tools.media import play_youtube
                    query = payload.get("query", "")
                    music = payload.get("music", False)
                    success, msg = play_youtube(query, music=music)
                    response_data = {"success": success, "message": msg}

                elif action == "prompt":
                    user_prompt = payload.get("prompt", "")
                    if user_prompt:
                        def _run_prompt(p: str):
                            try:
                                ui_state.update(state="thinking", thought="Processing user input...")
                                from agent import OSAgent
                                agent = OSAgent()
                                plan, results = agent.run(p)
                                if plan.response:
                                    from voice import speak
                                    speak(plan.response)
                            except Exception as err:
                                logger.error(f"Error processing web prompt: {err}")
                                ui_state.update(state="idle")

                        threading.Thread(target=_run_prompt, args=(user_prompt,), daemon=True).start()
                        response_data = {"success": True, "message": "Command dispatched to agent."}

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
            except Exception as e:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
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


def start_ui_server(port: int = PORT, open_browser: bool = False) -> ThreadingHTTPServer:
    """Starts the GLaDOS UI server in a daemon background thread."""
    server = ThreadingHTTPServer(("127.0.0.1", port), GLaDOSRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    logger.info(f"GLaDOS Visual UI active at {url}")

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    return server


if __name__ == "__main__":
    import time
    print(f"Starting Aperture Science GLaDOS UI on http://127.0.0.1:{PORT}...")
    start_ui_server(PORT, open_browser=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down UI server.")

