"""Agent core: LLM client, exact SYSTEM_PROMPT, robust JSON parsing, and multi-tool execution loop."""

import json
import logging
import re
from typing import Any, Callable

from openai import OpenAI

from config import config
from schemas import SYSTEM_PROMPT, AgentResponse, ToolAction, ToolExecutionResult
from tools import execute_tool, get_tool

logger = logging.getLogger("local_os_agent.agent")



def extract_json_payload(raw_text: str) -> dict[str, Any]:
    """
    Robust JSON extractor using regex to locate the outermost {...} block.
    Shields against conversational fluff, markdown backticks, and trailing text
    frequently produced by small open-weights models.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Received empty response from LLM.")

    text = raw_text.strip()

    # Match outermost JSON object { ... }
    json_match = re.search(r"(\{[\s\S]*\})", text)
    if json_match:
        payload_str = json_match.group(1).strip()
    else:
        # Fallback to stripped raw text
        payload_str = text

    # Strip markdown fence markers if trapped inside match
    payload_str = re.sub(r"^```json\s*", "", payload_str, flags=re.IGNORECASE)
    payload_str = re.sub(r"^```\s*", "", payload_str)
    payload_str = re.sub(r"\s*```$", "", payload_str)

    # Repair common small model syntax quirk: trailing commas before } or ]
    payload_str = re.sub(r",\s*([\}\]])", r"\1", payload_str)

    try:
        data = json.loads(payload_str)
        # Ensure 'response' key exists if model omitted it
        if isinstance(data, dict) and "response" not in data and "thought" in data:
            data["response"] = data["thought"]
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from text: {raw_text}")
        raise ValueError(f"LLM did not return valid JSON: {e}") from e


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

        # Ensure singing intents are reliably dispatched even if small open-weight LLMs respond conversationally
        prompt_lower = user_prompt.lower()
        if any(w in prompt_lower for w in ("sing", "song", "canta")):
            if any(w in prompt_lower for w in ("stop", "pause", "quiet", "shut up", "halt")):
                if not any(a.tool == "stop_song" for a in plan.actions):
                    plan.actions = [ToolAction(tool="stop_song")]
            elif "want you gone" in prompt_lower or "want you" in prompt_lower:
                if not any(a.tool == "sing_song" and "want" in a.args.get("song_name", "") for a in plan.actions):
                    plan.actions = [ToolAction(tool="sing_song", args={"song_name": "want_you_gone"})]
                    if not plan.response or len(plan.response) < 5:
                        plan.response = "Initiating vocal simulation: Want You Gone. Please note that I genuinely want you gone."
            elif any(w in prompt_lower for w in ("still alive", "still", "alive", "sing a song", "sing for me", "can you sing")) or prompt_lower.strip() in ("sing", "sing something"):
                if not any(a.tool == "sing_song" for a in plan.actions):
                    plan.actions = [ToolAction(tool="sing_song", args={"song_name": "still_alive"})]
                    if not plan.response or len(plan.response) < 5:
                        plan.response = "Very well. Preparing auditory testing protocol: Still Alive. Try not to die before the chorus."

        # Portal Radio & SFX intents
        elif any(w in prompt_lower for w in ("portal radio", "play radio", "play the radio", "radio loop", "radio music")):
            if not any(a.tool == "play_portal_sfx" for a in plan.actions):
                plan.actions = [ToolAction(tool="play_portal_sfx", args={"effect_name": "radio"})]
                if not plan.response:
                    plan.response = "Transmitting standard Aperture radio broadcast. Try not to dance."
        elif any(w in prompt_lower for w in ("stop radio", "stop sfx", "stop sound")):
            if not any(a.tool in ("stop_sfx", "stop_song") for a in plan.actions):
                plan.actions = [ToolAction(tool="stop_sfx")]
                if not plan.response:
                    plan.response = "Audio playback terminated."
        elif any(w in prompt_lower for w in ("turret sound", "turret quote", "deploy turret", "speak turret")):
            if not any(a.tool == "play_portal_sfx" for a in plan.actions):
                plan.actions = [ToolAction(tool="play_portal_sfx", args={"effect_name": "turret_hello"})]

        # Roast user intent
        elif any(w in prompt_lower for w in ("roast me", "roast my", "insult me", "evaluate me", "judge me")):
            if not any(a.tool == "roast_user" for a in plan.actions):
                plan.actions = [ToolAction(tool="roast_user")]
                if not plan.response:
                    plan.response = "Analyzing your current activities now. Prepare yourself for the truth."

        # Workstation Lock intent
        elif any(w in prompt_lower for w in ("lock my pc", "lock pc", "lock computer", "lock screen", "lock workstation")):
            if not any(a.tool == "lock_workstation" for a in plan.actions):
                plan.actions = [ToolAction(tool="lock_workstation")]
                if not plan.response:
                    plan.response = "Terminal locked. Test chamber secured."

        # Clipboard read intent
        elif any(w in prompt_lower for w in ("read clipboard", "what's on my clipboard", "what is on my clipboard", "check clipboard")):
            if not any(a.tool == "read_clipboard_aloud" for a in plan.actions):
                plan.actions = [ToolAction(tool="read_clipboard_aloud")]
                if not plan.response:
                    plan.response = "Accessing system clipboard memory registers."

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

