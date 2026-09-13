"""Agent core: LLM client, exact SYSTEM_PROMPT, robust JSON parsing, and multi-tool execution loop."""

import ast
import json
import logging
import re
from typing import Any, Callable

from openai import OpenAI

from config import config
from schemas import SYSTEM_PROMPT, AgentResponse, ToolAction, ToolExecutionResult
from tools import execute_tool, get_tool

logger = logging.getLogger("local_os_agent.agent")

# Pre-compiled regular expressions for high-performance JSON extraction & intent matching
RE_JSON_BLOCK = re.compile(r"(\{[\s\S]*\})")
RE_FENCE_JSON = re.compile(r"^```json\s*", re.IGNORECASE)
RE_FENCE_ANY = re.compile(r"^```\s*")
RE_FENCE_END = re.compile(r"\s*```$")
RE_TRAILING_COMMAS = re.compile(r",\s*([\}\]])")

# Pre-compiled intent patterns
RE_VOL_UP = re.compile(r"\b(volume up|louder|increase volume|higher volume|turn it up|sobe o volume|aumenta o volume|mais alto)\b", re.IGNORECASE)
RE_VOL_DOWN = re.compile(r"\b(volume down|quieter|lower volume|decrease volume|turn it down|abaixa o volume|diminui o volume|mais baixo)\b", re.IGNORECASE)
RE_VOL_EXACT = re.compile(r"\b(?:set|put|change)?\s*volume\s*(?:to|at|for|para|em)?\s*(\d{1,3})%?\b", re.IGNORECASE)
RE_MUTE = re.compile(r"\b(mute|unmute|silenciar|mudo|mutar|desmutar)\b", re.IGNORECASE)
RE_YT_CLEAN = re.compile(r"\b(play|search|on|for|in|no|na|tocar|ouvir|procurar|musica|music|youtube|de)\b", re.IGNORECASE)
RE_FLIGHT_MATCH = re.compile(r"(?:flight|voo|radar|aero|number|num|no)?\s*([A-Za-z]{2,3}\s*\d{1,4}[A-Za-z]?)", re.IGNORECASE)
RE_ALPHANUM_TOKEN = re.compile(r"\b[A-Za-z0-9]{3,7}\b")
RE_ZIMA_LAUNCH = re.compile(r"\b(?:launch|open|start|run|iniciar|abrir)\s+(?:app\s+)?([A-Za-z0-9_\-\s]+?)\s+(?:on|in|no|na)?\s*(?:zimaos|zima os|casaos|home server|servidor)\b", re.IGNORECASE)
RE_SCREENSHOT = re.compile(r"\b(screenshot|take screenshot|capture screen|captura de tela|tirar print|print da tela|screen capture)\b", re.IGNORECASE)
RE_STATS = re.compile(r"\b(system stats|system status|hardware stats|cpu usage|ram usage|status do sistema|como esta o pc|diagnostico)\b", re.IGNORECASE)
RE_RECYCLE = re.compile(r"\b(empty recycle bin|clean recycle bin|esvaziar lixeira|limpar lixeira)\b", re.IGNORECASE)
RE_WEATHER = re.compile(r"\b(weather|temperature|forecast|previsao do tempo|clima|temperatura)\b", re.IGNORECASE)


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
        self.base_url = base_url or config.llm_base_url
        self.api_key = api_key or config.llm_api_key
        self.model = model or config.llm_model
        self.enable_voice = enable_voice if enable_voice is not None else config.enable_tts
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        self.confirmation_callback = confirmation_callback or self._default_confirmation_prompt
        self.history: list[dict[str, str]] = []

    def _default_confirmation_prompt(self, thought: str, tool_name: str, args: dict[str, Any]) -> bool:
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
        # Multi-turn conversational memory: keep last 6 turns to maintain context
        recent_history = self.history[-6:]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *recent_history,
            {"role": "user", "content": user_prompt},
        ]

        logger.debug(f"Sending request to LLM ({self.model}) at {self.base_url}")
        # Optimized options to cap KV cache VRAM footprint to < 300MB
        extra_options = {
            "options": {
                "num_ctx": config.llm_num_ctx,
                "num_predict": config.llm_max_tokens,
            }
        }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,  # Slight temperature for natural eloquent phrasing
                timeout=config.llm_timeout,
                extra_body=extra_options,
            )
            content = response.choices[0].message.content or ""
            logger.debug(f"Raw LLM output:\n{content}")
            parsed_json = extract_json_payload(content)
            plan = AgentResponse.model_validate(parsed_json)
        except Exception as e:
            logger.warning(f"LLM query failed or produced invalid JSON ({e}). Falling back to deterministic resolver.")
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
        elif "youtube music" in prompt_lower or ("music" in prompt_lower and "youtube" in prompt_lower):
            clean_q = RE_YT_CLEAN.sub("", prompt_lower).strip()
            clean_q = clean_q or "aperture science"
            plan.actions = [ToolAction(tool="play_youtube", args={"query": clean_q, "music": True})]
            plan.response = f"Searching YouTube Music for {clean_q}. Melancholy suits your test scores."
        elif "youtube" in prompt_lower and any(w in prompt_lower for w in ("play", "search", "open", "watch", "tocar", "ver", "assistir", "procurar")):
            clean_q = RE_YT_CLEAN.sub("", prompt_lower).strip()
            clean_q = clean_q or "aperture science"
            plan.actions = [ToolAction(tool="play_youtube", args={"query": clean_q, "music": False})]
            plan.response = f"Searching YouTube for {clean_q}."

        # 3. Flightradar24 Flight Tracking
        elif any(w in prompt_lower for w in ("flight", "flightradar", "voo", "radar")) and any(w in prompt_lower for w in ("track", "where", "status", "rastrear", "rastreie", "onde", "qual")):
            flight_match = RE_FLIGHT_MATCH.search(prompt_lower)
            flight_code = "AA100"
            if flight_match and len(flight_match.group(1).strip()) >= 3:
                flight_code = flight_match.group(1).replace(" ", "").upper()
            else:
                tokens = RE_ALPHANUM_TOKEN.findall(prompt_lower)
                for t in tokens:
                    if any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
                        flight_code = t.upper()
                        break

            plan.actions = [ToolAction(tool="track_flight", args={"flight_query": flight_code, "open_browser": True})]
            plan.response = f"Accessing Flightradar telemetry for flight {flight_code}. Let us hope gravity behaves."

        # 4. ZimaOS Server & App Launcher
        elif any(w in prompt_lower for w in ("zimaos", "zima os", "casaos", "home server", "meu servidor", "servidor")):
            launch_match = RE_ZIMA_LAUNCH.search(prompt_lower)
            if launch_match and launch_match.group(1).strip() not in ("dashboard", "painel", "web", "gui", "interface", "server", "servidor"):
                target_app = launch_match.group(1).strip()
                plan.actions = [ToolAction(tool="launch_zimaos_app", args={"app_name": target_app})]
                plan.response = f"Accessing ZimaOS node to initialize container: {target_app}."
            elif any(w in prompt_lower for w in ("dashboard", "painel", "web", "gui", "open", "abrir", "interface")):
                plan.actions = [ToolAction(tool="open_zimaos_dashboard")]
                plan.response = "Opening ZimaOS management dashboard."
            elif any(w in prompt_lower for w in ("apps", "app", "container", "containers", "docker", "dockers", "aplicativos")):
                plan.actions = [ToolAction(tool="list_zimaos_apps")]
                plan.response = "Retrieving container manifest from ZimaOS."
            else:
                plan.actions = [ToolAction(tool="get_zimaos_status")]
                plan.response = "Querying ZimaOS telemetry. Calculating odds of catastrophic node failure."

        # 5. Singing Songs
        elif any(w in prompt_lower for w in ("sing", "song", "canta")):
            if any(w in prompt_lower for w in ("stop", "pause", "quiet", "shut up", "halt")):
                plan.actions = [ToolAction(tool="stop_song")]
                plan.response = "Song playback terminated."
            elif "want you gone" in prompt_lower or "want you" in prompt_lower:
                plan.actions = [ToolAction(tool="sing_song", args={"song_name": "want_you_gone"})]
                plan.response = "Initiating vocal simulation: Want You Gone. Please note that I genuinely want you gone."
            elif any(w in prompt_lower for w in ("still alive", "still", "alive", "sing a song", "sing for me", "can you sing")) or prompt_lower.strip() in ("sing", "sing something"):
                plan.actions = [ToolAction(tool="sing_song", args={"song_name": "still_alive"})]
                plan.response = "Very well. Preparing auditory testing protocol: Still Alive. Try not to die before the chorus."

        # 6. Portal Radio & SFX intents
        elif any(w in prompt_lower for w in ("portal radio", "play radio", "play the radio", "radio loop", "radio music")):
            plan.actions = [ToolAction(tool="play_portal_sfx", args={"effect_name": "radio"})]
            plan.response = "Transmitting standard Aperture radio broadcast. Try not to dance."
        elif any(w in prompt_lower for w in ("stop radio", "stop sfx", "stop sound")):
            plan.actions = [ToolAction(tool="stop_sfx")]
            plan.response = "Audio playback terminated."
        elif any(w in prompt_lower for w in ("turret sound", "turret quote", "deploy turret", "speak turret")):
            plan.actions = [ToolAction(tool="play_portal_sfx", args={"effect_name": "turret_hello"})]
            plan.response = "Deploying automated turret audio feed."

        # 7. Roast user intent
        elif any(w in prompt_lower for w in ("roast me", "roast my", "insult me", "evaluate me", "judge me")):
            plan.actions = [ToolAction(tool="roast_user")]
            plan.response = "Analyzing your current activities now. Prepare yourself for the truth."

        # 8. Workstation Lock intent
        elif any(w in prompt_lower for w in ("lock my pc", "lock pc", "lock computer", "lock screen", "lock workstation")):
            plan.actions = [ToolAction(tool="lock_workstation")]
            plan.response = "Terminal locked. Test chamber secured."

        # 9. Clipboard read intent
        elif any(w in prompt_lower for w in ("read clipboard", "what's on my clipboard", "what is on my clipboard", "check clipboard")):
            plan.actions = [ToolAction(tool="read_clipboard_aloud")]
            plan.response = "Accessing system clipboard memory registers."

        # 10. Screenshot intent
        elif RE_SCREENSHOT.search(prompt_lower):
            if not any(a.tool == "take_screenshot" for a in plan.actions):
                plan.actions = [ToolAction(tool="take_screenshot")]
                plan.response = "Capturing screen optical telemetry for analysis."

        # 11. System stats intent
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

            elif act.tool == "track_flight":
                if "flight_query" not in act.args and "flight" in act.args:
                    act.args["flight_query"] = act.args.pop("flight")
                if "flight_query" not in act.args:
                    act.args["flight_query"] = "AA100"
                act.args["flight_query"] = str(act.args["flight_query"]).strip()

            elif act.tool == "play_youtube":
                if "query" not in act.args:
                    act.args["query"] = "aperture science"
                act.args["query"] = str(act.args["query"]).strip()
                if "music" in act.args and not isinstance(act.args["music"], bool):
                    act.args["music"] = str(act.args["music"]).lower() in ("true", "1", "yes")

            elif act.tool == "launch_zimaos_app":
                if "app_name" not in act.args and "app" in act.args:
                    act.args["app_name"] = act.args.pop("app")
                if "app_name" in act.args:
                    act.args["app_name"] = str(act.args["app_name"]).strip()

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

