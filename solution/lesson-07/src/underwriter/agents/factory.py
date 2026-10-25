"""Pick the underwriting agent from configuration.

    AGENT_MODE=tools (default)   bounded tool-calling agent (lesson 4)
    AGENT_MODE=single            one structured call plus one repair (lesson 3)
"""

from __future__ import annotations

import os

from underwriter.llm.config import get_llm_client
from underwriter.workflow.contracts import UnderwritingAgent


def get_agent(mode: str | None = None, llm_fault: str | None = None) -> UnderwritingAgent:
    mode = (mode or os.environ.get("AGENT_MODE", "tools")).lower()
    client = get_llm_client(fault=llm_fault)
    if mode == "single":
        from underwriter.agents.underwriting import LLMUnderwritingAgent
        return LLMUnderwritingAgent(client)
    if mode == "tools":
        from underwriter.agents.tool_agent import ToolUsingUnderwritingAgent
        return ToolUsingUnderwritingAgent(client)
    raise ValueError(f"AGENT_MODE must be 'tools' or 'single', not {mode!r}")
