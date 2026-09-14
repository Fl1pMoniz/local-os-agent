"""Agent core: LLM client, exact SYSTEM_PROMPT, robust JSON parsing, and multi-tool execution loop."""

import ast
import json
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from config import config
from schemas import (
    CONTAINER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    AgentResponse,
    ToolAction,
    ToolExecutionResult,
)
from tools import execute_tool, get_tool

logger = logging.getLogger("local_os_agent.agent")

# Suppress noisy HTTP client loggers to keep console output clean and free of [INFO] lines
for _noisy in ("httpx", "httpcore", "openai", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Pre-compiled regular expressions for high-performance JSON extraction & intent matching
RE_JSON_BLOCK = re.compile(r"(\{[\s\S]*\})")
RE_FENCE_JSON = re.compile(r"^```json\s*", re.IGNORECASE)
RE_FENCE_ANY = re.compile(r"^```\s*")
RE_FENCE_END = re.compile(r"\s*```$")
RE_TRAILING_COMMAS = re.compile(r",\s*([\}\]])")

# Pre-compiled intent patterns
RE_VOL_UP = re.compile(
    r"\b(volume up|louder|increase volume|higher volume|turn it up|sobe o volume|aumenta o volume|mais alto)\b",
    re.IGNORECASE,
)
RE_VOL_DOWN = re.compile(
    r"\b(volume down|quieter|lower volume|decrease volume|turn it down|abaixa o volume|diminui o volume|mais baixo)\b",
    re.IGNORECASE,
)
RE_VOL_EXACT = re.compile(
    r"\b(?:set|put|change)?\s*volume\s*(?:to|at|for|para|em)?\s*(\d{1,3})%?\b",
    re.IGNORECASE,
)
RE_MUTE = re.compile(r"\b(mute|unmute|silenciar|mudo|mutar|desmutar)\b", re.IGNORECASE)
RE_YT_CLEAN = re.compile(
    r"\b(play|search|on|for|in|no|na|tocar|ouvir|procurar|musica|music|youtube|de)\b",
    re.IGNORECASE,
)
RE_FLIGHT_MATCH = re.compile(
    r"(?:flight|voo|radar|aero|number|num|no)?\s*([A-Za-z]{2,3}\s*\d{1,4}[A-Za-z]?)",
    re.IGNORECASE,
)
RE_ALPHANUM_TOKEN = re.compile(r"\b[A-Za-z0-9]{3,7}\b")
RE_ZIMA_LAUNCH = re.compile(
    r"(?:\b(?:launch|open|start|run|iniciar|abrir)\s+(?:app\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:on|in|no|na)?\s*(?:zimaos|zima os|zima|casaos|home server|server|servidor)\b|\b(?:zimaos|zima os|zima|server|servidor)\s+(?:launch|open|start|run|abrir|iniciar)\s+(?:app\s+)?([A-Za-z0-9_\-\s]+)\b)",
    re.IGNORECASE,
)
RE_ZIMA_SSH = re.compile(
    r"\b(?:open|launch|start|run|connect|conectar|iniciar|abrir)?\s*(?:zimaos|zima|home server|server|servidor)?\s*(?:ssh|terminal ssh|ssh terminal|remote terminal|terminal remoto|remote shell|shell remoto)\b",
    re.IGNORECASE,
)
RE_IP_ADDRESS = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b")
RE_ZIMA_IP = re.compile(
    r"\b(?:change|set|update|configure|mudar|alterar|trocar|configurar)?\s*(?:zimaos|zima os|zima|server|servidor)?\s*(?:ip|host|address|endereco)?\s*(?:to|para|=|:)?\s*(\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?)\b",
    re.IGNORECASE,
)
RE_SCREENSHOT = re.compile(
    r"\b(screenshot|take screenshot|capture screen|captura de tela|tirar print|print da tela|screen capture)\b",
    re.IGNORECASE,
)
RE_HW_MONITOR = re.compile(
    r"\b(hardware|component|components|cpu temp|gpu temp|vram|power draw|temperatures|live tracker|pc monitor|hardware monitor|monitor pc|pc stats|thermal|temperatura|consumo|component usage|glados stats|ai stats|ai telemetry|tokens|tok/s|inference stats|ai ram)\b",
    re.IGNORECASE,
)
RE_STATS = re.compile(
    r"\b(system stats|system status|hardware stats|cpu usage|ram usage|status do sistema|como esta o pc|diagnostico)\b",
    re.IGNORECASE,
)
RE_RECYCLE = re.compile(
    r"\b(empty recycle bin|clean recycle bin|esvaziar lixeira|limpar lixeira)\b",
    re.IGNORECASE,
)
RE_WEATHER = re.compile(
    r"\b(weather|temperature|forecast|previsao do tempo|clima|temperatura)\b",
    re.IGNORECASE,
)
RE_CLIP = re.compile(
    r"\b(clip\s+(?:that|the\s+last|this|30)|record\s+(?:that|the\s+last|this|clip)|save\s+clip|salvar\s+clip)\b",
    re.IGNORECASE,
)
RE_CLIPS_LIST = re.compile(
    r"\b(recent\s+clips|list\s+clips|my\s+clips|highlights|ver\s+clips)\b",
    re.IGNORECASE,
)
RE_JELLYFIN = re.compile(
    r"(?:\b(?:play|search|watch|assistir|tocar)\s+(.+?)\s+(?:on|in|no|na)\s*(?:jellyfin|server|servidor)\b|\bjellyfin\s+(?:play|watch|search)?\s*(.+)\b)",
    re.IGNORECASE,
)
RE_JELLYFIN_STATUS = re.compile(
    r"\b(jellyfin\s+status|media\s+status|now\s+playing|what\s+is\s+playing|o\s+que\s+esta\s+tocando)\b",
    re.IGNORECASE,
)
RE_VISION = re.compile(
    r"\b(look\s+at|inspect\s+(?:this|my\s+screen|error|code)|what\s+is\s+this\s+error|diagnose\s+screen|roast\s+(?:my\s+screen|this|code))\b",
    re.IGNORECASE,
)
RE_SOUNDBOARD = re.compile(
    r"\b(?:(?:play|tocar|ouvir|executar|broadcast)\s+(?:a\s+|an\s+|the\s+)?(?:cave\s+johnson|wheatley|lemons|combustible\s+lemons|space\s+core|turret|neurotoxin)\s*(?:voiceline|voice\s+clip|audio\s+clip|quote|sound|clip)?|(?:cave\s+johnson|wheatley|lemons|space\s+core|turret|neurotoxin)\s+(?:voiceline|voice\s+clip|audio\s+clip|soundboard)|soundboard(?:\s+[a-z_]+)?)\b",
    re.IGNORECASE,
)
RE_DISCORD_CLIP = re.compile(
    r"\b(send\s+(?:clip|highlight)\s+to\s+discord|share\s+clip|post\s+clip\s+to\s+discord)\b",
    re.IGNORECASE,
)
RE_WELLNESS = re.compile(
    r"\b(subject\s+status|check\s+subject|hydration|ergonomics|wellness|posture|health\s+status|status\s+do\s+sujeito)\b",
    re.IGNORECASE,
)
RE_WATER = re.compile(
    r"\b(log\s+water|drink\s+water|drank\s+water|bebi\s+agua|tomar\s+agua)\b",
    re.IGNORECASE,
)


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    """
    Robust JSON extractor using regex to locate the outermost {...} block.
    Shields against conversational fluff, markdown backticks, single-quote dictionaries,
    and trailing commas produced by small open-weights models.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Received empty response from LLM.")

    text = raw_text.strip()

    # Match outermost JSON object { ... }
    json_match = RE_JSON_BLOCK.search(text)
    if json_match:
        payload_str = json_match.group(1).strip()
    else:
        # Fallback to stripped raw text
        payload_str = text

    # Strip markdown fence markers if trapped inside match
    payload_str = RE_FENCE_JSON.sub("", payload_str)
    payload_str = RE_FENCE_ANY.sub("", payload_str)
    payload_str = RE_FENCE_END.sub("", payload_str)

    # Repair common small model syntax quirk: trailing commas before } or ]
    payload_str = RE_TRAILING_COMMAS.sub(r"\1", payload_str)

    data: Any = None
    try:
        data = json.loads(payload_str)
    except json.JSONDecodeError:
        # 1. Fallback: attempt safe Python literal evaluation (handles single quotes & True/False)
        try:
            data = ast.literal_eval(payload_str)
        except Exception:
            # 2. Fallback: normalize single quotes and Python boolean literals
            try:
                normalized = re.sub(r"(?<!\\)'", '"', payload_str)
                normalized = re.sub(r"\bTrue\b", "true", normalized)
                normalized = re.sub(r"\bFalse\b", "false", normalized)
                normalized = re.sub(r"\bNone\b", "null", normalized)
                data = json.loads(normalized)
            except Exception as e:
                logger.error(f"Failed to decode JSON from text: {raw_text}")
                raise ValueError(f"LLM did not return valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Extracted payload is not a JSON object: {type(data)}")

    # Ensure required keys exist
    if "thought" not in data and "response" in data:
        data["thought"] = data["response"]
    elif "thought" not in data:
        data["thought"] = "Executing command."

    if "response" not in data:
        data["response"] = data.get("thought", "")

    if "actions" not in data or not isinstance(data["actions"], list):
        data["actions"] = []

    return data


ganza: int = "string"


class OSAgent:
    """Production-ready OS Agent orchestrating LLM queries and multi-tool execution."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enable_voice: bool | None = None,
        confirmation_callback: Callable[[str, str, dict[str, Any]], bool] | None = None,
    ):
        from tools.ai_telemetry import get_working_ollama_base_url

        self.base_url = base_url or get_working_ollama_base_url()
        self.api_key = api_key or config.llm_api_key
        self.model = model or config.llm_model
        self.enable_voice = enable_voice if enable_voice is not None else config.enable_tts
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key, max_retries=1)
        self.confirmation_callback = confirmation_callback or self._default_confirmation_prompt
        self.history: list[dict[str, str]] = []

    def _default_confirmation_prompt(
        self, thought: str, tool_name: str, args: dict[str, Any]
    ) -> bool:
        """Contextual confirmation prompt displaying the LLM's thought alongside the sensitive action."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
        if self.enable_voice:
            from voice import speak

            speak("Aperture Science safety protocol requires your confirmation for this action.")

        print("\n" + "=" * 60)
        print(" [!] SAFETY GATEKEEPER CONFIRMATION REQUIRED")
        print(f" Thought: {thought}")
        print(f" Action : {tool_name}({args_str})")
        print("=" * 60)
        try:
            choice = input(f"Execute {tool_name}({args_str})? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            return False

    def query_llm(self, user_prompt: str) -> AgentResponse:
        """Sends the prompt to the local LLM and returns the parsed AgentResponse."""
        # Multi-turn conversational memory: keep last 4-6 turns to maintain context and conserve tokens
        history_turns = 4 if config.cli_mode else 6
        recent_history = self.history[-history_turns:]
        # Select prompt tuned for headless/container mode to avoid evaluating 3000 tokens on CPU
        is_container = (
            config.container_mode
            or config.headless
            or os.getenv("CONTAINER_MODE", "false").lower() in ("true", "1")
        )
        sys_prompt = CONTAINER_SYSTEM_PROMPT if is_container else SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": sys_prompt},
            *recent_history,
            {"role": "user", "content": user_prompt},
        ]

        logger.debug(f"Sending request to LLM ({self.model}) at {self.base_url}")

        # Compute dynamic CPU thread cap: keep at least 2 cores free for host/ZimaOS
        num_threads = config.llm_num_threads
        if num_threads <= 0:
            try:
                import psutil

                cores = psutil.cpu_count(logical=False) or 4
                num_threads = max(1, cores - 2 if cores >= 6 else cores - 1)
            except Exception:
                num_threads = 4

        # Optimized options to cap KV cache VRAM footprint and CPU threads
        extra_options = {
            "options": {
                "num_ctx": config.llm_num_ctx,
                "num_predict": config.llm_max_tokens,
                "num_thread": num_threads,
            }
        }

        t_start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,  # Slight temperature for natural eloquent phrasing
                timeout=config.llm_timeout,
                extra_body=extra_options,
            )
            elapsed_s = time.time() - t_start
            content = response.choices[0].message.content or ""
            logger.debug(f"Raw LLM output:\n{content}")
            parsed_json = extract_json_payload(content)
            plan = AgentResponse.model_validate(parsed_json)

            # Record AI inference metrics into central telemetry tracker
            try:
                from tools.ai_telemetry import ai_tracker

                usage = getattr(response, "usage", None)
                p_tok = getattr(usage, "prompt_tokens", 0) if usage else len(str(messages).split())
                c_tok = getattr(usage, "completion_tokens", 0) if usage else len(content.split())
                ai_tracker.record_inference(
                    prompt_tokens=p_tok or 0,
                    completion_tokens=c_tok or 0,
                    latency_s=elapsed_s,
                    model=self.model,
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning(
                f"LLM query failed or produced invalid JSON ({e}). Falling back to deterministic resolver."
            )
            try:
                import tools.ai_telemetry as ait

                ait._working_ollama_base_url = None
            except Exception:
                pass
            plan = AgentResponse(
                thought="Executing Aperture Science deterministic rule engine.",
                response="Command acknowledged. Executing protocol.",
                actions=[],
            )

        prompt_lower = user_prompt.lower()

        # 1. Volume Controls (Relative, Exact, Mute)
        rel_up_match = RE_VOL_UP.search(prompt_lower)
        rel_down_match = RE_VOL_DOWN.search(prompt_lower)
        exact_vol_match = RE_VOL_EXACT.search(prompt_lower)

        if rel_up_match:
            plan.actions = [ToolAction(tool="change_volume_relative", args={"delta": 15})]
            plan.response = "Increasing volume. Do try not to rupture your eardrums."
        elif rel_down_match:
            plan.actions = [ToolAction(tool="change_volume_relative", args={"delta": -15})]
            plan.response = "Decreasing volume. Silence is scientifically preferable anyway."
        elif exact_vol_match:
            vol_val = max(0, min(100, int(exact_vol_match.group(1))))
            plan.actions = [ToolAction(tool="set_volume", args={"level": vol_val})]
            plan.response = f"Volume adjusted to {vol_val} percent. Efficiency maximized."
        elif RE_MUTE.search(prompt_lower):
            if not any(a.tool == "mute_toggle" for a in plan.actions):
                plan.actions = [ToolAction(tool="mute_toggle")]
                plan.response = "Toggling audio mute register."

        # 2. YouTube Music and YouTube Video
        elif (
            "youtube music" in prompt_lower
            or "music.youtube" in prompt_lower
            or (
                "music" in prompt_lower
                and any(
                    w in prompt_lower
                    for w in (
                        "youtube",
                        "play",
                        "open",
                        "start",
                        "listen",
                        "tocar",
                        "ouvir",
                    )
                )
            )
            or (
                "song" in prompt_lower
                and any(
                    w in prompt_lower
                    for w in (
                        "youtube",
                        "play",
                        "open",
                        "start",
                        "listen",
                        "tocar",
                        "ouvir",
                    )
                )
            )
        ):
            from tools.media import clean_youtube_query

            clean_q = clean_youtube_query(prompt_lower)
            clean_q = clean_q or "Still Alive Portal"
            plan.actions = [ToolAction(tool="play_youtube", args={"query": clean_q, "music": True})]
            plan.response = f"Opening YouTube Music to directly stream '{clean_q}'. Melancholy suits your test scores."
        elif "youtube" in prompt_lower and any(
            w in prompt_lower
            for w in (
                "play",
                "search",
                "open",
                "watch",
                "tocar",
                "ver",
                "assistir",
                "procurar",
            )
        ):
            from tools.media import clean_youtube_query

            clean_q = clean_youtube_query(prompt_lower)
            clean_q = clean_q or "aperture science"
            plan.actions = [
                ToolAction(tool="play_youtube", args={"query": clean_q, "music": False})
            ]
            plan.response = f"Opening YouTube to directly stream '{clean_q}'."

        # 3. Flightradar24 Flight Tracking & Telemetry
        elif any(w in prompt_lower for w in ("flight", "flightradar", "voo", "radar")):
            # Check if user is asking for the currently tracked flight telemetry
            is_tracked_query = any(
                phrase in prompt_lower
                for phrase in (
                    "tracked flight",
                    "tracked flights",
                    "flight info",
                    "flight telemetry",
                    "radar telemetry",
                    "radar status",
                    "current flight",
                    "what flight",
                    "voo rastreado",
                    "info do voo",
                    "status do voo",
                    "telemetria",
                )
            ) or (
                any(
                    w in prompt_lower
                    for w in (
                        "info",
                        "informacao",
                        "status",
                        "telemetry",
                        "telemetria",
                        "details",
                        "detalhes",
                    )
                )
                and not any(c.isdigit() for c in prompt_lower)
            )

            flight_match = RE_FLIGHT_MATCH.search(prompt_lower) if not is_tracked_query else None
            flight_code = None
            if (
                flight_match
                and len(flight_match.group(1).strip()) >= 3
                and any(c.isdigit() for c in flight_match.group(1))
            ):
                flight_code = flight_match.group(1).replace(" ", "").upper()
            elif not is_tracked_query:
                tokens = RE_ALPHANUM_TOKEN.findall(prompt_lower)
                for t in tokens:
                    if any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
                        flight_code = t.upper()
                        break

            if flight_code:
                open_browser = (
                    False
                    if config.cli_mode
                    else any(
                        w in prompt_lower
                        for w in (
                            "browser",
                            "open",
                            "abrir",
                            "navegador",
                            "map",
                            "mapa",
                        )
                    )
                )
                plan.actions = [
                    ToolAction(
                        tool="track_flight",
                        args={
                            "flight_query": flight_code,
                            "open_browser": open_browser,
                        },
                    )
                ]
                plan.response = f"Accessing Flightradar telemetry for flight {flight_code}. Let us hope gravity behaves."
            elif is_tracked_query or any(
                w in prompt_lower for w in ("track", "where", "status", "onde", "rastrear")
            ):
                plan.actions = [ToolAction(tool="get_tracked_flight_info")]
                plan.response = (
                    "Querying Aperture Science radar telemetry for currently tracked flight."
                )

        # 4. ZimaOS Server & App Launcher
        elif any(
            w in prompt_lower
            for w in (
                "zimaos",
                "zima os",
                "zima",
                "casaos",
                "home server",
                "server",
                "meu servidor",
                "servidor",
            )
        ) or (
            RE_IP_ADDRESS.search(prompt_lower)
            and any(w in prompt_lower for w in ("ip", "host", "address", "server"))
        ):
            ip_match = RE_IP_ADDRESS.search(prompt_lower)
            if (
                any(
                    w in prompt_lower
                    for w in (
                        "ip",
                        "host",
                        "address",
                        "endereco",
                        "mudar",
                        "change",
                        "set",
                        "update",
                    )
                )
                and ip_match
            ):
                new_ip = ip_match.group(0).strip()
                plan.actions = [ToolAction(tool="set_zimaos_host", args={"new_host": new_ip})]
                plan.response = f"Updating ZimaOS network endpoint registers to {new_ip}."
            elif RE_ZIMA_SSH.search(prompt_lower) or (
                any(w in prompt_lower for w in ("ssh", "shell", "terminal"))
                and any(w in prompt_lower for w in ("server", "servidor", "zima", "zimaos"))
            ):
                plan.actions = [ToolAction(tool="open_zimaos_ssh")]
                plan.response = (
                    "Initializing secure remote shell protocol to Aperture Science mainframe."
                )
            else:
                launch_match = RE_ZIMA_LAUNCH.search(prompt_lower)
                target_app = (
                    (launch_match.group(1) or launch_match.group(2) or "").strip()
                    if launch_match
                    else ""
                )
                if target_app and target_app not in (
                    "dashboard",
                    "painel",
                    "web",
                    "gui",
                    "interface",
                    "server",
                    "servidor",
                    "ssh",
                    "terminal",
                ):
                    plan.actions = [
                        ToolAction(tool="launch_zimaos_app", args={"app_name": target_app})
                    ]
                    plan.response = f"Accessing ZimaOS node to initialize container: {target_app}."
                elif any(
                    w in prompt_lower
                    for w in (
                        "dashboard",
                        "painel",
                        "web",
                        "gui",
                        "open",
                        "abrir",
                        "interface",
                    )
                ):
                    plan.actions = [ToolAction(tool="open_zimaos_dashboard")]
                    plan.response = "Opening ZimaOS management dashboard."
                elif any(
                    w in prompt_lower
                    for w in (
                        "apps",
                        "app",
                        "container",
                        "containers",
                        "docker",
                        "dockers",
                        "aplicativos",
                    )
                ):
                    plan.actions = [ToolAction(tool="list_zimaos_apps")]
                    plan.response = "Retrieving container manifest from ZimaOS."
                elif any(
                    w in prompt_lower
                    for w in ("monitor", "live", "telemetry", "hud", "track", "painel")
                ):
                    is_live = any(
                        w in prompt_lower for w in ("live", "real-time", "real time", "continuo")
                    )
                    plan.actions = [ToolAction(tool="monitor_zimaos", args={"live": is_live})]
                    plan.response = "Querying ZimaOS server telemetry."
                else:
                    plan.actions = [ToolAction(tool="get_zimaos_status")]
                    plan.response = (
                        "Querying ZimaOS telemetry. Calculating odds of catastrophic node failure."
                    )

        # 5. Singing Songs
        elif any(w in prompt_lower for w in ("sing", "song", "canta")):
            if any(w in prompt_lower for w in ("stop", "pause", "quiet", "shut up", "halt")):
                plan.actions = [ToolAction(tool="stop_song")]
                plan.response = "Song playback terminated."
            elif "want you gone" in prompt_lower or "want you" in prompt_lower:
                plan.actions = [ToolAction(tool="sing_song", args={"song_name": "want_you_gone"})]
                plan.response = "Initiating vocal simulation: Want You Gone. Please note that I genuinely want you gone."
            elif any(
                w in prompt_lower
                for w in (
                    "still alive",
                    "still",
                    "alive",
                    "sing a song",
                    "sing for me",
                    "can you sing",
                )
            ) or prompt_lower.strip() in ("sing", "sing something"):
                plan.actions = [ToolAction(tool="sing_song", args={"song_name": "still_alive"})]
                plan.response = "Very well. Preparing auditory testing protocol: Still Alive. Try not to die before the chorus."

        # 6. Portal Radio & SFX intents
        elif any(
            w in prompt_lower
            for w in (
                "portal radio",
                "play radio",
                "play the radio",
                "radio loop",
                "radio music",
            )
        ):
            plan.actions = [ToolAction(tool="play_portal_sfx", args={"effect_name": "radio"})]
            plan.response = "Transmitting standard Aperture radio broadcast. Try not to dance."
        elif any(w in prompt_lower for w in ("stop radio", "stop sfx", "stop sound")):
            plan.actions = [ToolAction(tool="stop_sfx")]
            plan.response = "Audio playback terminated."
        elif any(
            w in prompt_lower
            for w in ("turret sound", "turret quote", "deploy turret", "speak turret")
        ):
            plan.actions = [
                ToolAction(tool="play_portal_sfx", args={"effect_name": "turret_hello"})
            ]
            plan.response = "Deploying automated turret audio feed."

        # 7. Roast user intent
        elif any(
            w in prompt_lower
            for w in ("roast me", "roast my", "insult me", "evaluate me", "judge me")
        ):
            plan.actions = [ToolAction(tool="roast_user")]
            plan.response = "Analyzing your current activities now. Prepare yourself for the truth."

        # 8. Voice Recognition and Voice Audio Control intents
        elif any(
            phrase in prompt_lower
            for phrase in (
                "turn on voice recognition",
                "start voice recognition",
                "enable voice recognition",
                "turn on voice",
                "voice on",
                "enable listening",
                "listen on",
                "activate voice recognition",
            )
        ):
            from ui.server import start_voice_listener

            start_voice_listener()
            plan.actions = []
            plan.response = (
                "Voice recognition activated. Local microphone telemetry listener engaged."
            )

        elif any(
            phrase in prompt_lower
            for phrase in (
                "turn off voice recognition",
                "stop voice recognition",
                "disable voice recognition",
                "turn off voice",
                "voice off",
                "stop listening",
                "disable listening",
                "deactivate voice recognition",
            )
        ):
            from ui.server import stop_voice_listener

            stop_voice_listener()
            plan.actions = []
            plan.response = "Voice recognition deactivated. Microphone telemetry sensor offline."

        elif any(
            phrase in prompt_lower
            for phrase in (
                "turn on glados voice",
                "enable glados voice",
                "tts on",
                "unmute glados",
                "turn on speech",
                "enable voice output",
                "voice audio on",
                "enable tts",
            )
        ):
            config.enable_tts = True
            try:
                from ui.state import ui_state

                ui_state.update(glados_voice=True)
            except Exception:
                pass
            plan.actions = []
            plan.response = (
                "Acoustic speech synthesis re-enabled. My vocal outputs are once again active."
            )

        elif any(
            phrase in prompt_lower
            for phrase in (
                "turn off glados voice",
                "disable glados voice",
                "tts off",
                "mute glados",
                "turn off speech",
                "mute voice",
                "voice audio off",
                "disable voice output",
                "disable tts",
            )
        ):
            config.enable_tts = False
            try:
                from ui.state import ui_state

                ui_state.update(glados_voice=False)
            except Exception:
                pass
            plan.actions = []
            plan.response = (
                "Acoustic speech synthesis inhibited. Operating in text-only transmission mode."
            )

        elif any(
            phrase in prompt_lower
            for phrase in (
                "open webpage",
                "open web console",
                "launch ui",
                "launch web",
                "open ui",
                "start web",
                "open dashboard",
                "open glados web",
                "open browser interface",
            )
        ):
            from ui.server import start_ui_server

            start_ui_server(port=5000, open_browser=True)
            plan.actions = []
            plan.response = "Initializing Aperture Science ASCII Web Console on host port 5000."

        # 9. Workstation Lock intent
        elif any(
            w in prompt_lower
            for w in (
                "lock my pc",
                "lock pc",
                "lock computer",
                "lock screen",
                "lock workstation",
            )
        ):
            plan.actions = [ToolAction(tool="lock_workstation")]
            plan.response = "Terminal locked. Test chamber secured."

        # 9. Clipboard read intent
        elif any(
            w in prompt_lower
            for w in (
                "read clipboard",
                "what's on my clipboard",
                "what is on my clipboard",
                "check clipboard",
            )
        ):
            plan.actions = [ToolAction(tool="read_clipboard_aloud")]
            plan.response = "Accessing system clipboard memory registers."

        # 10. Screenshot intent
        elif RE_SCREENSHOT.search(prompt_lower):
            if not any(a.tool == "take_screenshot" for a in plan.actions):
                plan.actions = [ToolAction(tool="take_screenshot")]
                plan.response = "Capturing screen optical telemetry for analysis."

        # 11. Hardware telemetry / live monitor intent
        elif RE_HW_MONITOR.search(prompt_lower):
            is_live = any(
                w in prompt_lower
                for w in (
                    "live",
                    "tracker",
                    "real time",
                    "real-time",
                    "continuo",
                    "monitorar",
                )
            )
            if not any(a.tool == "monitor_hardware" for a in plan.actions):
                plan.actions = [ToolAction(tool="monitor_hardware", args={"live": is_live})]
                plan.response = "Querying host component thermal and utilization sensors."

        # 12. System stats intent
        elif RE_STATS.search(prompt_lower):
            if not any(a.tool == "get_system_stats" for a in plan.actions):
                plan.actions = [ToolAction(tool="get_system_stats")]
                plan.response = "Gathering diagnostic telemetry from host computer."

        # 12. Empty recycle bin intent
        elif RE_RECYCLE.search(prompt_lower):
            if not any(a.tool == "empty_recycle_bin" for a in plan.actions):
                plan.actions = [ToolAction(tool="empty_recycle_bin")]
                plan.response = "Purging digital incinerator registers permanently."

        # 13. Weather intent
        elif RE_WEATHER.search(prompt_lower):
            if not any(a.tool == "get_weather" for a in plan.actions):
                plan.actions = [ToolAction(tool="get_weather")]
                plan.response = "Querying atmospheric sensors for environmental conditions."

        # 14. Protocol 2: 30-Second Gameplay Clipper
        elif RE_CLIP.search(prompt_lower):
            plan.actions = [ToolAction(tool="capture_game_clip", args={"seconds": 30})]
            plan.response = "Accessing OBS Replay Buffer to archive test highlight."

        elif RE_CLIPS_LIST.search(prompt_lower):
            plan.actions = [ToolAction(tool="list_recent_clips")]
            plan.response = "Retrieving catalog of recently recorded gameplay highlights."

        # 15. Protocol 1: Jellyfin Media Dispatcher
        elif "jellyfin" in prompt_lower or (
            "media" in prompt_lower
            and any(
                w in prompt_lower
                for w in ("play", "stream", "server", "watch", "assistir", "tocar")
            )
        ):
            if any(w in prompt_lower for w in ("now playing", "status", "what is playing", "info")):
                plan.actions = [ToolAction(tool="get_jellyfin_now_playing")]
                plan.response = "Accessing live Jellyfin media telemetry on the server."
            else:
                j_match = RE_JELLYFIN.search(prompt_lower)
                q = (
                    (j_match.group(1) or j_match.group(2)).strip()
                    if j_match
                    else prompt_lower.replace("jellyfin", "").strip()
                )
                plan.actions = [
                    ToolAction(tool="search_and_play_jellyfin", args={"query": q or "media"})
                ]
                plan.response = f"Dispatching media stream for '{q}' on Jellyfin."

        # 16. Protocol 3: Optical Screen Vision & Error Inspection
        elif RE_VISION.search(prompt_lower):
            plan.actions = [ToolAction(tool="analyze_screen", args={"prompt": user_prompt.strip()})]
            plan.response = "Engaging optical sensor. Analyzing your screen for errors and cognitive deficiencies."

        # 17. Protocol 4: Soundboard
        elif RE_SOUNDBOARD.search(prompt_lower):
            clip_key = "lemons"
            if "moron" in prompt_lower or "punch" in prompt_lower:
                clip_key = "wheatley_moron"
            elif "wheatley" in prompt_lower or "hello" in prompt_lower:
                clip_key = "wheatley_hello"
            elif "space" in prompt_lower:
                clip_key = "space"
            elif "neurotoxin" in prompt_lower:
                clip_key = "neurotoxin"
            elif "turret" in prompt_lower or "sorry" in prompt_lower or "blame" in prompt_lower:
                clip_key = "turret_sorry"
            plan.actions = [ToolAction(tool="play_soundboard", args={"clip_name": clip_key})]
            plan.response = f"Broadcasting Aperture acoustic synthesizer: {clip_key}."

        # 18. Protocol 6: Discord Clip Dispatch
        elif RE_DISCORD_CLIP.search(prompt_lower):
            plan.actions = [ToolAction(tool="send_clip_to_discord")]
            plan.response = "Transmitting newest game highlight to Aperture Discord relay."

        # 19. Protocol 7: Subject Maintenance & Wellness
        elif RE_WATER.search(prompt_lower):
            plan.actions = [ToolAction(tool="log_water_intake")]
            plan.response = "Hydration event logged in biological testing registry."

        elif RE_WELLNESS.search(prompt_lower):
            plan.actions = [ToolAction(tool="check_subject_status")]
            plan.response = "Retrieving test subject biometric and compliance telemetry."

        # Normalize and sanitize arguments for any LLM-emitted actions
        for act in plan.actions:
            if act.tool == "set_volume":
                # Normalize arguments like 'volume', 'value' -> 'level'
                if "level" not in act.args:
                    for k in ("volume", "value", "val", "pct"):
                        if k in act.args:
                            try:
                                clean_val = str(act.args.pop(k)).replace("%", "").strip()
                                act.args["level"] = int(float(clean_val))
                                break
                            except (ValueError, TypeError):
                                pass
                if "level" not in act.args:
                    act.args["level"] = 50
                else:
                    try:
                        clean_val = str(act.args["level"]).replace("%", "").strip()
                        act.args["level"] = max(0, min(100, int(float(clean_val))))
                    except (ValueError, TypeError):
                        act.args["level"] = 50

            elif act.tool == "change_volume_relative":
                if "delta" in act.args:
                    try:
                        clean_d = str(act.args["delta"]).replace("%", "").strip()
                        act.args["delta"] = int(float(clean_d))
                    except (ValueError, TypeError):
                        act.args["delta"] = 10

            elif act.tool == "get_tracked_flight_info":
                act.args = {}

            elif act.tool == "track_flight":
                if "flight_query" not in act.args and "flight" in act.args:
                    act.args["flight_query"] = act.args.pop("flight")
                if "flight_query" not in act.args:
                    act.args["flight_query"] = "AA100"
                act.args["flight_query"] = str(act.args["flight_query"]).strip()
                if config.cli_mode:
                    act.args["open_browser"] = False

            elif act.tool == "play_youtube":
                if "query" not in act.args:
                    act.args["query"] = "aperture science"
                act.args["query"] = str(act.args["query"]).strip()
                if "music" in act.args and not isinstance(act.args["music"], bool):
                    act.args["music"] = str(act.args["music"]).lower() in (
                        "true",
                        "1",
                        "yes",
                    )

            elif act.tool == "launch_zimaos_app":
                if "app_name" not in act.args and "app" in act.args:
                    act.args["app_name"] = act.args.pop("app")
                if "app_name" in act.args:
                    act.args["app_name"] = str(act.args["app_name"]).strip()

            elif act.tool == "monitor_hardware":
                if "live" in act.args and not isinstance(act.args["live"], bool):
                    act.args["live"] = str(act.args["live"]).lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                elif "live" not in act.args:
                    act.args["live"] = False

            elif act.tool == "monitor_zimaos":
                if "live" in act.args and not isinstance(act.args["live"], bool):
                    act.args["live"] = str(act.args["live"]).lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                elif "live" not in act.args:
                    act.args["live"] = False

            elif act.tool == "set_zimaos_host":
                if "new_host" not in act.args:
                    for k in ("host", "ip", "address", "url", "server"):
                        if k in act.args:
                            act.args["new_host"] = str(act.args.pop(k)).strip()
                            break
                if "new_host" in act.args:
                    act.args["new_host"] = str(act.args["new_host"]).strip()
                else:
                    act.args["new_host"] = "192.168.1.123"

        # Update conversation history
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": json.dumps(plan.model_dump())})

        return plan

    def execute_plan(
        self,
        plan: AgentResponse,
        on_action_start: Callable[[ToolAction], None] | None = None,
        on_action_finish: Callable[[ToolExecutionResult], None] | None = None,
    ) -> list[ToolExecutionResult]:
        """
        Executes a sequence of tool actions from the agent's plan,
        supporting the contextual safety gatekeeper confirmation flow.
        """
        results: list[ToolExecutionResult] = []

        if not plan.actions:
            logger.info(f"Agent decided no actions needed. Thought: {plan.thought}")
            return results

        for action in plan.actions:
            if on_action_start:
                on_action_start(action)

            tool_def = get_tool(action.tool)
            bypass = False

            if tool_def and tool_def.sensitive:
                # Ask user with contextual thought
                approved = self.confirmation_callback(plan.thought, action.tool, action.args)
                if not approved:
                    res = ToolExecutionResult(
                        tool=action.tool,
                        args=action.args,
                        success=False,
                        status="cancelled",
                        message="User declined execution.",
                    )
                    results.append(res)
                    if on_action_finish:
                        on_action_finish(res)
                    continue
                else:
                    bypass = True

            res = execute_tool(action.tool, action.args, bypass_confirmation=bypass)
            results.append(res)
            if on_action_finish:
                on_action_finish(res)

        return results

    def run(self, user_prompt: str) -> tuple[AgentResponse, list[ToolExecutionResult]]:
        """Convenience method to query the LLM and execute the resulting plan."""
        plan = self.query_llm(user_prompt)
        results = self.execute_plan(plan)
        return plan, results
