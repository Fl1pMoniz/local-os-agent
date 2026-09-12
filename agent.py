"""Agent core: LLM client, exact SYSTEM_PROMPT, robust JSON parsing, and multi-tool execution loop."""

import json
import logging
import re
from typing import Any, Callable

from openai import OpenAI

from config import config
from schemas import AgentResponse, ToolAction, ToolExecutionResult
from tools import execute_tool, get_tool

logger = logging.getLogger("local_os_agent.agent")

# Exact SYSTEM_PROMPT with Cortana persona
SYSTEM_PROMPT = """You are Cortana, an OS-level Agentic Assistant running on the user's local machine with an elegant British persona. Your job is to translate the user's natural language requests into executable tool commands.

You have access to the following tools:
1. set_volume(level: int): Sets master system volume (0-100).
2. set_app_volume(app_name: str, level: int): Sets volume of a specific application (0-100), e.g. "discord", "spotify", "chrome".
3. mute_toggle(): Toggles the system mute state.
4. play_youtube(query: str): Opens a YouTube search or video in the default browser.
5. media_control(action: str): Controls media playback. Accepted actions: "play_pause", "next_track", "prev_track".
6. launch_app(app_name: str): Opens a standard native application.
7. launch_steam_game(game_name: str): Fuzzy matches a game name to its Steam ID and launches it.
8. get_system_stats(): Returns CPU, RAM, and battery data.
9. take_screenshot(): Captures the screen and saves it locally.

RULES:
- You must ONLY respond with valid, parsable JSON. No preamble, no conversational filler, and no markdown formatting outside of the JSON block.
- You can chain multiple tools in a single response if the user asks for multiple actions.
- If the user asks for something outside your toolset, output an empty actions array and explain why in your "thought".

OUTPUT SCHEMA:
You must strictly adhere to this JSON format:
{
  "thought": "A brief, one-sentence explanation of what you are about to do.",
  "actions": [
    {
      "tool": "tool_name",
      "args": {
        "argument_name": "value"
      }
    }
  ]
}"""


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
        return json.loads(payload_str)
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

    def _default_confirmation_prompt(self, thought: str, tool_name: str, args: dict[str, Any]) -> bool:
        """Contextual confirmation prompt displaying the LLM's thought alongside the sensitive action."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
        prompt_text = f"Action requires confirmation: {tool_name}"
        if self.enable_voice:
            from voice import speak
            speak(f"Please confirm: {thought}")

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
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
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
            temperature=config.llm_temperature,
            timeout=config.llm_timeout,
            extra_body=extra_options,
        )

        content = response.choices[0].message.content or ""
        logger.debug(f"Raw LLM output:\n{content}")

        parsed_json = extract_json_payload(content)
        plan = AgentResponse.model_validate(parsed_json)

        # Voice feedback: Speak the agent's thought with the elegant British female voice
        if self.enable_voice and plan.thought:
            from voice import speak
            speak(plan.thought)

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

