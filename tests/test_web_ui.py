"""Unit tests for the Aperture Science GLaDOS Web UI, telemetry endpoints, and voice controls."""

import json
import re
import unittest
import urllib.request
from pathlib import Path

from config import config
from ui.server import start_ui_server
from ui.state import ui_state

# Unicode regex to detect any emojis (Supplemental Symbols, Pictographs, Emoticons)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    "\U0001F680-\U0001F6FF"  # Transport and Map
    "\U0001F700-\U0001F77F"  # Alchemical Symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


class TestWebUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_port = 5088
        cls.server = start_ui_server(port=cls.test_port, open_browser=False)
        cls.base_url = f"http://127.0.0.1:{cls.test_port}"

    def test_index_html_exists_and_has_no_emojis(self):
        """Verifies that index.html exists, has the Aperture ASCII logo, and ZERO emojis."""
        index_file = Path(__file__).resolve().parent.parent / "ui" / "index.html"
        self.assertTrue(index_file.exists(), "ui/index.html must exist.")
        content = index_file.read_text(encoding="utf-8")

        # Must not contain emojis
        emojis_found = EMOJI_PATTERN.findall(content)
        self.assertEqual(len(emojis_found), 0, f"Found prohibited emojis in index.html: {emojis_found}")

        # Must contain Aperture ASCII logo and key Aperture keywords
        self.assertIn("APERTURE SCIENCE", content.upper())
        self.assertIn(".------------.", content)  # Aperture Diaphragm ASCII
        self.assertIn("H@@@MM@M#H", content)      # Picture 2 Aperture ASCII Logo signature
        self.assertIn("GLADOS-WEB", content.upper())
        self.assertIn("[MIC:", content)
        self.assertIn("[VOICE:", content)
        self.assertIn("PC STATS", content)
        self.assertIn("ZIMAOS", content)

    def test_get_index_html_via_http(self):
        """Tests that GET / returns the HTML page correctly."""
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = resp.read().decode("utf-8")
            self.assertIn("Aperture Science Laboratories", data)

    def test_get_state_endpoint(self):
        """Tests GET /api/state returns valid state including voice & telemetry keys."""
        req = urllib.request.Request(f"{self.base_url}/api/state")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("state", data)
            self.assertIn("voice_recognition", data)
            self.assertIn("glados_voice", data)
            self.assertIn("active_telemetry_tab", data)

    def test_get_telemetry_endpoint(self):
        """Tests GET /api/telemetry returns hardware, zimaos, and flight keys."""
        req = urllib.request.Request(f"{self.base_url}/api/telemetry")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("hardware", data)
            self.assertIn("zimaos", data)
            self.assertIn("voice_recognition", data)
            self.assertIn("glados_voice", data)

    def test_voice_control_endpoints(self):
        """Tests GET & POST /api/voice_control."""
        # 1. GET
        req = urllib.request.Request(f"{self.base_url}/api/voice_control")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("voice_recognition", data)
            self.assertIn("glados_voice", data)

        # 2. POST to disable TTS
        post_body = json.dumps({"glados_voice": False}).encode("utf-8")
        post_req = urllib.request.Request(
            f"{self.base_url}/api/voice_control",
            data=post_body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(post_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertFalse(data.get("glados_voice"))
            self.assertFalse(config.enable_tts)

        # 3. POST to re-enable TTS
        post_body = json.dumps({"glados_voice": True}).encode("utf-8")
        post_req = urllib.request.Request(
            f"{self.base_url}/api/voice_control",
            data=post_body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(post_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("glados_voice"))
            self.assertTrue(config.enable_tts)

    def test_post_action_tab_switcher(self):
        """Tests POST /api/action with set_active_telemetry_tab."""
        for tab in ("zimaos", "pc"):
            post_body = json.dumps({"action": "set_active_telemetry_tab", "tab": tab}).encode("utf-8")
            post_req = urllib.request.Request(
                f"{self.base_url}/api/action",
                data=post_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(post_req, timeout=3.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertEqual(data.get("active_tab"), tab)
                self.assertEqual(ui_state.active_telemetry_tab, tab)

    def test_terminal_events_and_voice_sync(self):
        """Tests that voice execution events are recorded and delivered to the web console."""
        # 1. Record a synthetic voice execution event in ui_state
        event = ui_state.record_terminal_event(
            source="voice",
            command="launch jellyfin on zimaos",
            output="[+] launch_zimaos_app: Launched Jellyfin on ZimaOS",
            response="Accessing ZimaOS node.",
            tools=[{"tool": "launch_zimaos_app", "success": True, "message": "Launched Jellyfin"}],
        )
        self.assertIsNotNone(event.get("id"))
        self.assertEqual(event.get("source"), "voice")
        self.assertEqual(event.get("command"), "launch jellyfin on zimaos")

        # 2. Query /api/state to verify terminal_events are exposed
        req_state = urllib.request.Request(f"{self.base_url}/api/state")
        with urllib.request.urlopen(req_state, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("terminal_events", data)
            matching = [e for e in data["terminal_events"] if e.get("id") == event["id"]]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["source"], "voice")

        # 3. Query /api/telemetry to verify terminal_events are included
        req_telem = urllib.request.Request(f"{self.base_url}/api/telemetry")
        with urllib.request.urlopen(req_telem, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("terminal_events", data)
            matching = [e for e in data["terminal_events"] if e.get("id") == event["id"]]
            self.assertEqual(len(matching), 1)


if __name__ == "__main__":
    unittest.main()

