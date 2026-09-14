"""Unit tests for GLaDOS expanded toolset and intent routing."""

import time
import unittest
from unittest.mock import MagicMock, patch

from agent import OSAgent
from tools.companion import get_active_window, roast_user
from tools.sfx import VPK_SFX_MAP, get_sfx_path, stop_sfx
from tools.system import (
    get_clipboard,
    get_hardware_telemetry,
    get_system_stats,
    monitor_hardware,
    run_live_system_monitor,
    set_clipboard,
    set_timer,
)
from tools.web import KNOWN_URL_ALIASES, open_website


class TestExpandedTools(unittest.TestCase):
    def test_known_website_aliases(self):
        self.assertIn("youtube", KNOWN_URL_ALIASES)
        self.assertIn("github", KNOWN_URL_ALIASES)
        self.assertIn("portal wiki", KNOWN_URL_ALIASES)

    @patch("webbrowser.open")
    def test_open_website(self, mock_open):
        mock_open.return_value = True
        success, msg = open_website("youtube")
        self.assertTrue(success)
        mock_open.assert_called_with("https://www.youtube.com")

        success2, msg2 = open_website("quantum computing")
        self.assertTrue(success2)
        self.assertIn("google.com/search", msg2)

    def test_active_window_and_roast(self):
        success, win_info = get_active_window()
        self.assertTrue(success)
        self.assertIn("Active Window:", win_info)

        success_roast, roast = roast_user()
        self.assertTrue(success_roast)
        self.assertIsInstance(roast, str)
        self.assertGreater(len(roast), 10)

    def test_sfx_resolution_and_maps(self):
        self.assertIn("radio", VPK_SFX_MAP)
        self.assertIn("turret_hello", VPK_SFX_MAP)
        # Verify get_sfx_path returns a Path or None without crashing
        _path = get_sfx_path("radio")
        # stop_sfx should succeed safely
        stop_success, stop_msg = stop_sfx()
        self.assertTrue(stop_success)

    def test_system_stats_gpu_telemetry(self):
        success, stats = get_system_stats()
        self.assertTrue(success)
        self.assertIn("cpu", stats)
        self.assertIn("ram", stats)
        self.assertIn("battery", stats)
        self.assertIn("gpu", stats)
        if stats["gpu"] is not None:
            self.assertIn("device", stats["gpu"])
            self.assertIn("allocated_mb", stats["gpu"])

    def test_hardware_monitor_telemetry(self):
        # 1. Test telemetry data collection
        telemetry = get_hardware_telemetry()
        self.assertIsInstance(telemetry, dict)
        self.assertIn("cpu", telemetry)
        self.assertIn("ram", telemetry)
        self.assertIn("disk", telemetry)
        self.assertIn("uptime", telemetry)
        self.assertIn("hud_card", telemetry)

        cpu = telemetry["cpu"]
        self.assertIn("percent", cpu)
        self.assertIn("physical_cores", cpu)
        self.assertIn("logical_cores", cpu)
        self.assertIn("temp_c", cpu)
        self.assertGreaterEqual(cpu["temp_c"], 0)

        ram = telemetry["ram"]
        self.assertIn("total_gb", ram)
        self.assertIn("used_gb", ram)
        self.assertIn("percent", ram)
        self.assertGreater(ram["total_gb"], 0)

        # 2. Test tool execution
        success, res = monitor_hardware(live=False)
        self.assertTrue(success)
        self.assertIn("hud_card", res)
        self.assertIn("APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD", res["hud_card"])
        self.assertIn("GLaDOS AI NEURAL CORE & INFERENCE TELEMETRY", res["hud_card"])
        self.assertIn("glados_ai", res)
        self.assertIn("ai_ram_total_mb", res["glados_ai"])
        self.assertIn("tokens_per_sec", res["glados_ai"])
        self.assertIn("total_tokens_produced", res["glados_ai"])

        # 3. Test bounded live monitor loop
        try:
            run_live_system_monitor(interval=0.01, max_ticks=2)
        except Exception as e:
            self.fail(f"run_live_system_monitor raised exception: {e}")

    def test_clipboard_operations(self):
        test_string = "Aperture Science Portal Gun Protocol 99"
        set_ok, set_msg = set_clipboard(test_string)
        self.assertTrue(set_ok)

        get_ok, content = get_clipboard()
        self.assertTrue(get_ok)
        self.assertEqual(content, test_string)

    def test_set_timer_validation(self):
        success, msg = set_timer(10, label="Cake baking")
        self.assertTrue(success)
        self.assertIn("10 seconds", msg)

        fail_success, fail_msg = set_timer(-5)
        self.assertFalse(fail_success)


class TestAgentDeterministicIntents(unittest.TestCase):
    @patch("openai.resources.chat.completions.Completions.create")
    def test_intent_intercepts(self, mock_create):
        # Configure mock LLM response with default conversational reply
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"thought": "Processing", "response": "Yes, test subject?", "actions": []}'
                )
            )
        ]
        mock_create.return_value = mock_response

        agent = OSAgent(enable_voice=False)

        # Test roast intent
        plan = agent.query_llm("GLaDOS roast me please")
        self.assertTrue(any(a.tool == "roast_user" for a in plan.actions))

        # Test portal radio intent
        plan = agent.query_llm("GLaDOS play the portal radio")
        self.assertTrue(
            any(
                a.tool == "play_portal_sfx" and a.args.get("effect_name") == "radio"
                for a in plan.actions
            )
        )

        # Test stop radio
        plan = agent.query_llm("GLaDOS stop radio now")
        self.assertTrue(any(a.tool == "stop_sfx" for a in plan.actions))

        # Test lock PC intent
        plan = agent.query_llm("GLaDOS lock my pc")
        self.assertTrue(any(a.tool == "lock_workstation" for a in plan.actions))

        # Test read clipboard intent
        plan = agent.query_llm("GLaDOS read clipboard aloud")
        self.assertTrue(any(a.tool == "read_clipboard_aloud" for a in plan.actions))

        # Test volume relative up & down
        plan_up = agent.query_llm("GLaDOS volume up please")
        self.assertTrue(
            any(
                a.tool == "change_volume_relative" and a.args.get("delta") == 15
                for a in plan_up.actions
            )
        )

        plan_down = agent.query_llm("GLaDOS turn it down")
        self.assertTrue(
            any(
                a.tool == "change_volume_relative" and a.args.get("delta") == -15
                for a in plan_down.actions
            )
        )

        plan_exact = agent.query_llm("GLaDOS set volume to 40%")
        self.assertTrue(
            any(a.tool == "set_volume" and a.args.get("level") == 40 for a in plan_exact.actions)
        )

        # Test YouTube Music vs regular YouTube
        plan_ytm = agent.query_llm("GLaDOS play Radiohead on youtube music")
        self.assertTrue(
            any(a.tool == "play_youtube" and a.args.get("music") is True for a in plan_ytm.actions)
        )

        plan_yt = agent.query_llm("GLaDOS search portal trailer on youtube")
        self.assertTrue(
            any(a.tool == "play_youtube" and a.args.get("music") is False for a in plan_yt.actions)
        )

        # Test Flightradar24 tracking intent
        plan_flight = agent.query_llm("GLaDOS track flight AA100")
        self.assertTrue(
            any(
                a.tool == "track_flight" and "AA100" in a.args.get("flight_query", "")
                for a in plan_flight.actions
            )
        )

        # Test Flight telemetry vs tracking queries
        plan_tracked = agent.query_llm("GLaDOS info on tracked flight")
        self.assertTrue(any(a.tool == "get_tracked_flight_info" for a in plan_tracked.actions))

        plan_what_flight = agent.query_llm("GLaDOS what flight are you tracking?")
        self.assertTrue(any(a.tool == "get_tracked_flight_info" for a in plan_what_flight.actions))

        plan_telemetry = agent.query_llm("GLaDOS show flight telemetry")
        self.assertTrue(any(a.tool == "get_tracked_flight_info" for a in plan_telemetry.actions))

        # Test ZimaOS server intent
        plan_zima = agent.query_llm("GLaDOS check my ZimaOS server")
        self.assertTrue(any(a.tool == "get_zimaos_status" for a in plan_zima.actions))

        plan_zima_apps = agent.query_llm("GLaDOS check ZimaOS containers")
        self.assertTrue(any(a.tool == "list_zimaos_apps" for a in plan_zima_apps.actions))

        plan_zima_dash = agent.query_llm("GLaDOS open ZimaOS dashboard")
        self.assertTrue(any(a.tool == "open_zimaos_dashboard" for a in plan_zima_dash.actions))

        plan_zima_launch = agent.query_llm("GLaDOS launch Plex on ZimaOS")
        self.assertTrue(
            any(
                a.tool == "launch_zimaos_app" and "plex" in a.args.get("app_name", "").lower()
                for a in plan_zima_launch.actions
            )
        )

        # Test hardware monitor intent
        plan_hw_live = agent.query_llm(
            "I want a tool for a live tracker of my pc component usage and temps"
        )
        self.assertTrue(
            any(
                a.tool == "monitor_hardware" and a.args.get("live") is True
                for a in plan_hw_live.actions
            )
        )

        plan_hw = agent.query_llm("GLaDOS show pc component usage and temps")
        self.assertTrue(any(a.tool == "monitor_hardware" for a in plan_hw.actions))


class TestNewTools(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_track_flight_mock(self, mock_urlopen):
        from tools.flight import track_flight

        # Mock FR24 JSON response with type: live
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"results": [{"id": "live_123", "type": "live", "label": "AA100 (AAL100)", "detail": {"callsign": "AAL100", "route": "JFK-LHR", "aircraft": "B772", "lat": 40.64, "lon": -73.77}}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = track_flight("AA100", open_browser=False)
        self.assertTrue(success)
        self.assertIn("AA100", msg)

        # Check that ui_state has tracked_flight set
        from ui.state import ui_state

        state = ui_state.get_state()
        self.assertIsNotNone(state.get("tracked_flight"))
        self.assertEqual(state["tracked_flight"]["callsign"], "AA100")

    def test_get_tracked_flight_info_hud(self):
        from tools.flight import get_tracked_flight_info
        from ui.state import ui_state

        test_flight = {
            "callsign": "DL450",
            "flight_number": "DAL450",
            "model": "Boeing 767-332(ER)",
            "origin": "ATL",
            "dest": "GRU",
            "altitude_ft": 35000,
            "speed_kts": 490,
            "speed_kmh": 907,
            "heading": 145,
            "reg": "N1200K",
            "status": "Cruising",
            "lat": -12.3456,
            "lon": -45.6789,
            "fr24_url": "https://www.flightradar24.com/DL450",
            "updated_at": time.time(),
        }
        ui_state.update(tracked_flight=test_flight)

        success, hud_output = get_tracked_flight_info(auto_refresh=False)
        self.assertTrue(success)
        self.assertIn("DL450", hud_output)
        self.assertIn("ATL -> GRU", hud_output)
        self.assertIn("35,000 FT", hud_output)
        self.assertIn("490 KTS", hud_output)
        self.assertIn("145° (SE)", hud_output)
        self.assertIn("Boeing 767-332(ER)", hud_output)
        self.assertIn("N1200K", hud_output)
        self.assertIn("CRUISING", hud_output)
        self.assertIn("https://www.flightradar24.com/DL450", hud_output)
        self.assertIn("-12.3456°, -45.6789°", hud_output)

        # Verify all 11 HUD fields are present and match website interface
        required_fields = [
            "Callsign / Flight",
            "Airspace Route",
            "Radar Status",
            "Predicted Landing",
            "Aircraft Model",
            "Registration",
            "Live Altitude",
            "Ground Speed",
            "Flight Heading",
            "Coordinates",
            "Live Radar URL",
        ]
        for field in required_fields:
            self.assertIn(field, hud_output)

    def test_haversine_and_eta_calculation(self):
        from tools.flight import calculate_predicted_landing, haversine_distance_nm

        # Distance between JFK (40.6413, -73.7781) and LHR (51.4700, -0.4543) ~ 3000 NM
        dist = haversine_distance_nm(40.6413, -73.7781, 51.4700, -0.4543)
        self.assertGreater(dist, 2900)
        self.assertLess(dist, 3200)

        # Cruising at 500 knots, 1000 NM away should predict approx 120-130 minutes
        # Lat 40, Lon -50 to Lat 40, Lon -30
        _dist_1000 = haversine_distance_nm(40.0, -50.0, 40.0, -30.0)
        minutes, eta_str = calculate_predicted_landing(40.0, -50.0, 500, "LHR", 35000)
        self.assertIsNotNone(minutes)
        self.assertGreater(minutes, 60)
        self.assertIn("min", eta_str)
        self.assertIn("UTC", eta_str)

    def test_track_flight_with_float_telemetry(self):
        """Verifies that float heading (e.g. from live sector feeds like AEA185) formats without ValueError."""
        from tools.flight import format_flight_telemetry

        float_telemetry = {
            "callsign": "AEA185",
            "flight_number": "AEA185",
            "model": "Boeing 787-9 Dreamliner",
            "origin": "MAD",
            "dest": "EZE",
            "altitude_ft": 37998.4,
            "speed_kts": 492.7,
            "speed_kmh": 912.5,
            "heading": 218.4,
            "reg": "EC-MSZ",
            "status": "Cruising",
            "lat": 14.8123,
            "lon": -24.5432,
            "fr24_url": "https://www.flightradar24.com/AEA185",
        }
        hud = format_flight_telemetry(float_telemetry)
        self.assertIn("AEA185", hud)
        self.assertIn("218° (SW)", hud)
        self.assertIn("37,998 FT", hud)
        self.assertIn("493 KTS", hud)
        self.assertIn("Predicted Landing", hud)

    def test_run_dynamic_flight_tracker_max_ticks(self):
        from tools.flight import run_dynamic_flight_tracker
        from ui.state import ui_state

        test_flight = {
            "callsign": "SAT442",
            "flight_number": "SP442",
            "model": "DH8D",
            "origin": "PDL",
            "dest": "HOR",
            "altitude_ft": 9750,
            "speed_kts": 233,
            "speed_kmh": 432,
            "heading": 294,
            "reg": "9H-LWA",
            "status": "Climbing",
            "lat": 37.9,
            "lon": -26.0,
            "predicted_minutes": 34,
            "eta_str": "34 min (ETA ~13:04 UTC)",
            "updated_at": 1789302644.0,
            "fr24_url": "https://www.flightradar24.com/SAT442",
        }
        ui_state.update(tracked_flight=test_flight)
        # Should execute exactly 1 tick and return cleanly without error
        run_dynamic_flight_tracker("SAT442", interval=0.01, max_ticks=1)

    @patch("urllib.request.urlopen")
    def test_zimaos_status_mock(self, mock_urlopen):
        from tools.zimaos import get_zimaos_status

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"cpu": {"model_name": "Intel N100", "usage": 12}, "memory": {"total": 8589934592, "used": 2147483648}}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, res = get_zimaos_status()
        self.assertTrue(success)
        self.assertIn("ZimaOS", res)

    @patch("webbrowser.open")
    def test_open_zimaos_dashboard(self, mock_open):
        from tools.zimaos import open_zimaos_dashboard

        mock_open.return_value = True
        success, msg = open_zimaos_dashboard()
        self.assertTrue(success)
        self.assertIn("ZimaOS dashboard", msg)

    @patch("webbrowser.open")
    @patch("urllib.request.urlopen")
    def test_launch_zimaos_app_mock(self, mock_urlopen, mock_browser):
        from tools.zimaos import launch_zimaos_app

        mock_browser.return_value = True

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": [{"name": "plex", "id": "cid_plex", "state": "running", "ports": [{"PublicPort": 32400}]}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = launch_zimaos_app("plex")
        self.assertTrue(success)
        self.assertIn("plex", msg.lower())

    @patch("webbrowser.open")
    def test_custom_zima_apps_crud_and_launch(self, mock_browser):
        from tools.zimaos import (
            add_custom_zima_app,
            delete_custom_zima_app,
            get_custom_zima_apps,
            launch_zimaos_app,
        )

        mock_browser.return_value = True

        # 1. Add custom app
        success, msg = add_custom_zima_app("TestPortainer", ":9000", "Management")
        self.assertTrue(success)
        self.assertIn("TestPortainer", msg)

        # 2. Retrieve custom apps
        apps = get_custom_zima_apps()
        matched = [a for a in apps if a.get("name") == "TestPortainer"]
        self.assertTrue(len(matched) >= 1)
        self.assertIn(":9000", matched[0]["url"])

        # 3. Launch custom app
        l_success, l_msg = launch_zimaos_app("TestPortainer")
        self.assertTrue(l_success)
        self.assertIn("TestPortainer", l_msg)
        mock_browser.assert_called()

        # 4. Delete custom app
        d_success, d_msg = delete_custom_zima_app("TestPortainer")
        self.assertTrue(d_success)
        self.assertIn("Removed", d_msg)

        # 5. Verify removal
        apps_after = get_custom_zima_apps()
        matched_after = [a for a in apps_after if a.get("name") == "TestPortainer"]
        self.assertEqual(len(matched_after), 0)

    @patch("webbrowser.open")
    def test_direct_youtube_music_playback(self, mock_browser):
        from tools.media import clean_youtube_query, play_youtube

        # Verify query cleaning
        self.assertEqual(
            clean_youtube_query(
                "open the song Bohemian Rhapsody and start playing it on youtube music"
            ),
            "Bohemian Rhapsody",
        )
        self.assertEqual(
            clean_youtube_query("start playing Still Alive on youtube music"), "Still Alive"
        )
        self.assertEqual(
            clean_youtube_query("open the song and start playing it on youtube music"),
            "Still Alive Portal",
        )

        # Verify direct playback URL construction
        success, msg = play_youtube("Bohemian Rhapsody Queen", music=True, open_browser=True)
        self.assertTrue(success)
        self.assertIn("YouTube Music", msg)
        mock_browser.assert_called()
        opened_url = mock_browser.call_args[0][0]
        self.assertTrue(opened_url.startswith("https://music.youtube.com/"))

    def test_zimaos_telemetry_hud(self):
        from tools.zimaos import format_zimaos_hud, get_zimaos_telemetry, monitor_zimaos

        # 1. Test telemetry structure
        telemetry = get_zimaos_telemetry()
        self.assertIsInstance(telemetry, dict)
        self.assertIn("host", telemetry)
        self.assertIn("online", telemetry)
        self.assertIn("hud_card", telemetry)

        # 2. Test HUD formatting with synthetic telemetry
        synth_data = {
            "host": "http://192.168.1.123",
            "online": True,
            "gateway": "ZimaOS-Gateway (12.5ms)",
            "cpu": {"percent": 15.2, "temp_c": 42.0, "model": "Intel N100"},
            "ram": {"total_gb": 16.0, "used_gb": 4.5, "percent": 28.1},
            "disk": {"total_gb": 512.0, "used_gb": 120.0, "percent": 23.4},
            "services": [
                {"port": 80, "name": "ZimaOS Web GUI"},
                {"port": 8123, "name": "Home Assistant"},
            ],
            "auth_status": "[* ACTIVE]",
        }
        hud = format_zimaos_hud(synth_data)
        self.assertIn("APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD", hud)
        self.assertIn("Intel N100", hud)
        self.assertIn("Home Assist", hud)

        # 3. Test tool wrapper
        success, res = monitor_zimaos(live=False)
        self.assertTrue(success)
        self.assertIsInstance(res, dict)
        self.assertIn("hud_card", res)

    def test_set_zimaos_host_tool(self):
        from config import config
        from tools.zimaos import get_zimaos_host, set_zimaos_host

        # Test changing to custom IP
        success, msg = set_zimaos_host("192.168.1.200")
        self.assertTrue(success)
        self.assertIn("192.168.1.200", msg)
        self.assertEqual(get_zimaos_host(), "http://192.168.1.200")

        # Test prefix stripping ("to 192.168.1.123")
        success, msg = set_zimaos_host("to 192.168.1.123")
        self.assertTrue(success)
        self.assertEqual(get_zimaos_host(), "http://192.168.1.123")
        self.assertEqual(config.zimaos_host, "http://192.168.1.123")

    def test_zimaos_live_runner(self):
        from tools.zimaos import run_live_zimaos_monitor

        # Bounded run of 1 tick should complete without exceptions
        try:
            run_live_zimaos_monitor(interval=0.01, max_ticks=1)
        except Exception as e:
            self.fail(f"run_live_zimaos_monitor raised exception: {e}")

    def test_zimaos_intent_routing(self):
        agent = OSAgent(enable_voice=False)

        # 1. Test live monitoring intent
        with patch.object(
            agent.client.chat.completions, "create", side_effect=Exception("LLM simulated offline")
        ):
            plan = agent.query_llm("monitor my zimaos server live")
            self.assertTrue(
                any(a.tool == "monitor_zimaos" and a.args.get("live") is True for a in plan.actions)
            )

        # 2. Test IP reconfiguration intent
        with patch.object(
            agent.client.chat.completions, "create", side_effect=Exception("LLM simulated offline")
        ):
            plan = agent.query_llm("change my zimaos ip to 192.168.1.123")
            self.assertTrue(
                any(
                    a.tool == "set_zimaos_host" and "192.168.1.123" in a.args.get("new_host", "")
                    for a in plan.actions
                )
            )

        # 3. Test generic zimaos check & monitor zimaos
        with patch.object(
            agent.client.chat.completions, "create", side_effect=Exception("LLM simulated offline")
        ):
            plan_mon = agent.query_llm("monitor zimaos")
            self.assertTrue(any(a.tool == "monitor_zimaos" for a in plan_mon.actions))

            plan_stat = agent.query_llm("zimaos")
            self.assertTrue(any(a.tool == "get_zimaos_status" for a in plan_stat.actions))


if __name__ == "__main__":
    unittest.main()
