from __future__ import annotations
from typing import Any, Dict, List, Protocol

class Agent(Protocol):
    name: str
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

class Orchestrator:
    def __init__(self, agents: List[Agent]):
        self.agents = {a.name: a for a in agents}

    def route(self, objective: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        # very simple router; can be replaced with policy/LLM later
        if objective in self.agents:
            return self.agents[objective].run(payload)
        # default fusion: run selected agents and combine results
        out: Dict[str, Any] = {"objective": objective, "agent_outputs": []}
        for a in self.agents.values():
            try:
                out["agent_outputs"].append({"agent": a.name, "output": a.run(payload)})
            except Exception as e:
                out["agent_outputs"].append({"agent": a.name, "error": str(e)})
        return out
