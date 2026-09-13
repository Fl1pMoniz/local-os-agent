"""Central state dispatcher for the GLaDOS visual UI."""

import json
import logging
import queue
import threading
from typing import Any

logger = logging.getLogger("local_os_agent.ui.state")


class AgentUIState:
    """Thread-safe UI state manager broadcasting real-time events to the web UI."""

    def __init__(self):
        self._lock = threading.Lock()
        self.state: str = "idle"  # "idle", "listening", "thinking", "speaking", "singing"
        self.text: str = ""
        self.song: str | None = None
        self.thought: str = ""
        self.tracked_flight: dict[str, Any] | None = None
        self.voice_recognition: bool = False
        self.glados_voice: bool = True
        self.active_telemetry_tab: str = "pc"  # "pc" or "zimaos"
        self.hardware_telemetry: dict[str, Any] | None = None
        self.zimaos_telemetry: dict[str, Any] | None = None
        self.terminal_events: list[dict[str, Any]] = []
        self._event_counter: int = 0
        self.subscribers: list[queue.Queue] = []

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "text": self.text,
                "song": self.song,
                "thought": self.thought,
                "tracked_flight": self.tracked_flight,
                "voice_recognition": self.voice_recognition,
                "glados_voice": self.glados_voice,
                "active_telemetry_tab": self.active_telemetry_tab,
                "hardware_telemetry": self.hardware_telemetry,
                "zimaos_telemetry": self.zimaos_telemetry,
                "terminal_events": list(self.terminal_events),
            }

    def record_terminal_event(
        self,
        source: str,
        command: str,
        output: str,
        response: str = "",
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Records a terminal/voice execution event and broadcasts it to all connected SSE clients."""
        import datetime
        with self._lock:
            self._event_counter += 1
            event = {
                "id": self._event_counter,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "source": source,
                "command": command,
                "output": output,
                "response": response,
                "tools": tools or [],
            }
            self.terminal_events.append(event)
            if len(self.terminal_events) > 100:
                self.terminal_events.pop(0)

            snapshot = {
                "type": "terminal_event",
                "terminal_event": event,
                "state": self.state,
                "text": self.text,
                "thought": self.thought,
                "tracked_flight": self.tracked_flight,
                "voice_recognition": self.voice_recognition,
                "glados_voice": self.glados_voice,
                "active_telemetry_tab": self.active_telemetry_tab,
                "hardware_telemetry": self.hardware_telemetry,
                "zimaos_telemetry": self.zimaos_telemetry,
            }

            dead = []
            for q in self.subscribers:
                try:
                    q.put_nowait(snapshot)
                except Exception:
                    dead.append(q)
            for d in dead:
                self.subscribers.remove(d)

            return event

    def update(
        self,
        state: str | None = None,
        text: str | None = None,
        song: str | None = None,
        thought: str | None = None,
        tracked_flight: dict[str, Any] | None = None,
        voice_recognition: bool | None = None,
        glados_voice: bool | None = None,
        active_telemetry_tab: str | None = None,
        hardware_telemetry: dict[str, Any] | None = None,
        zimaos_telemetry: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            if state is not None:
                self.state = state
            if text is not None:
                self.text = text
            if song is not None:
                self.song = song if song != "" else None
            if thought is not None:
                self.thought = thought
            if tracked_flight is not None:
                self.tracked_flight = tracked_flight
            if voice_recognition is not None:
                self.voice_recognition = voice_recognition
            if glados_voice is not None:
                self.glados_voice = glados_voice
            if active_telemetry_tab is not None:
                self.active_telemetry_tab = active_telemetry_tab
            if hardware_telemetry is not None:
                self.hardware_telemetry = hardware_telemetry
            if zimaos_telemetry is not None:
                self.zimaos_telemetry = zimaos_telemetry

            snapshot = {
                "state": self.state,
                "text": self.text,
                "song": self.song,
                "thought": self.thought,
                "tracked_flight": self.tracked_flight,
                "voice_recognition": self.voice_recognition,
                "glados_voice": self.glados_voice,
                "active_telemetry_tab": self.active_telemetry_tab,
                "hardware_telemetry": self.hardware_telemetry,
                "zimaos_telemetry": self.zimaos_telemetry,
            }

            # Broadcast to SSE subscribers
            dead = []
            for q in self.subscribers:
                try:
                    q.put_nowait(snapshot)
                except Exception:
                    dead.append(q)
            for d in dead:
                self.subscribers.remove(d)

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=50)
        with self._lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


ui_state = AgentUIState()

