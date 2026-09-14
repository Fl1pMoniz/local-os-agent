"""LangChain tool-calling agent implementation of IntentAgentPort.

Integrates ChatOpenAI (Ollama / LM Studio / OpenAI endpoints) with validated
LangChain tools, structured tool calling, and offline survival fallback resolution.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.agent.fallback import OfflineFallbackResolver
from app.agent.tools import ALL_GLADOS_TOOLS
from app.core.config import AppSettings, settings
from app.ports.agent import IntentAgentPort
from schemas import SYSTEM_PROMPT

logger = logging.getLogger("glados.agent.langchain")


class LangChainOSAgent(IntentAgentPort):
    """GLaDOS conversational desktop automation agent powered by LangChain."""

    def __init__(self, app_settings: AppSettings | None = None) -> None:
        self.settings = app_settings or settings
        self.fallback = OfflineFallbackResolver()
        self._tool_map = {t.name: t for t in ALL_GLADOS_TOOLS}

        # Configure LLM client targeting local (Ollama/LM Studio) or remote endpoint
        self.llm = ChatOpenAI(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key,  # type: ignore[arg-type]
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            timeout=self.settings.llm_timeout,
            max_tokens=self.settings.llm_max_tokens,
        )
        self.llm_with_tools = self.llm.bind_tools(ALL_GLADOS_TOOLS)

    def run(self, prompt: str) -> str:
        """Processes user instruction via offline fallback resolver or LangChain tool-calling."""
        if not prompt or not prompt.strip():
            return "Directive input cannot be blank. Please enter a valid test command."

        clean_prompt = prompt.strip()

        # Step 1: Check offline deterministic survival commands (zero LLM latency)
        if fb := self.fallback.resolve(clean_prompt):
            logger.info("Executed offline deterministic intercept for tool '%s'", fb.tool)
            self._execute_tool_by_name(fb.tool, fb.args)
            return fb.response

        # Step 2: Dispatch prompt to LangChain tool-calling model
        messages: list[Any] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=clean_prompt),
        ]

        try:
            response: AIMessage = self.llm_with_tools.invoke(messages)  # type: ignore[assignment]
        except Exception as exc:
            logger.warning("LLM call failed (%s). Attempting local execution fallback.", exc)
            return f"Encountered LLM endpoint communication failure: {exc}"

        # If model did not invoke any tools, return its textual conversational response
        if not response.tool_calls:
            return str(response.content)

        # Step 3: Execute tool calls requested by model
        executed_messages: list[str] = []
        messages.append(response)

        for tc in response.tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            call_id = tc.get("id", "call_1")

            logger.info("Executing tool '%s' with parameters %s", tool_name, tool_args)
            output = self._execute_tool_by_name(tool_name, tool_args)
            executed_messages.append(f"[{tool_name}]: {output}")

            messages.append(ToolMessage(content=output, tool_call_id=call_id))

        # Request final synthesis from LLM with tool outputs
        try:
            final_response = self.llm.invoke(messages)
            if final_response.content:
                return str(final_response.content)
        except Exception as exc:
            logger.debug("Final synthesis skipped: %s", exc)

        return "\n".join(executed_messages)

    def execute_command(self, command: str) -> tuple[bool, str]:
        """Directly parses and executes a tool command."""
        from tools import execute_tool

        # Fallback to direct tool execution registry
        return execute_tool(command)

    def _execute_tool_by_name(self, name: str, args: dict[str, Any]) -> str:
        """Invokes a registered tool by its function or LangChain identifier."""
        tool_func = self._tool_map.get(name) or self._tool_map.get(f"{name}_tool")
        if tool_func:
            try:
                result = tool_func.invoke(args)
                return str(result)
            except Exception as exc:
                return f"Tool {name} execution failed: {exc}"

        from tools import execute_tool

        success, msg = execute_tool(name, **args)
        return msg
