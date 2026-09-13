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
        self.subscribers: list[queue.Queue] = []

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "text": self.text,
                "song": self.song,
                "thought": self.thought,
                "tracked_flight": self.tracked_flight,
            }

    def update(
        self,
        state: str | None = None,
        text: str | None = None,
        song: str | None = None,
        thought: str | None = None,
        tracked_flight: dict[str, Any] | None = None,
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

            snapshot = {
                "state": self.state,
                "text": self.text,
                "song": self.song,
                "thought": self.thought,
                "tracked_flight": self.tracked_flight,
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

