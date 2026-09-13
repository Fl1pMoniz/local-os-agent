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

        elif parsed.path == "/assets/glados.png":
            img_file = UI_DIR / "assets" / "glados.png"
            if img_file.exists():
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(img_file, "rb") as f:
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

