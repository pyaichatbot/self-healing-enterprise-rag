from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from shrag.generate.llm import complete


@dataclass(slots=True)
class ToolResult:
    output: str
    metadata: dict[str, str] = field(default_factory=dict)


class Tool(Protocol):
    name: str
    description: str

    def run(self, tool_input: str) -> ToolResult: ...


@dataclass(slots=True)
class ReActStep:
    thought: str
    action: str
    action_input: str
    observation: str


@dataclass(slots=True)
class ReActAgent:
    tools: tuple[Tool, ...]
    max_steps: int = 6
    
    def _execute_action(self, tool_map: dict[str, Tool], action: str, action_input: str) -> str:
        tool = tool_map.get(action)
        if tool is None:
            return f"Unknown tool: {action}"
        try:
            result = tool.run(action_input)
            return result.output
        except Exception as exc:  # noqa: BLE001
            return f"Tool error: {exc}"

    def run(self, query: str) -> tuple[str, tuple[ReActStep, ...]]:
        steps: list[ReActStep] = []
        tool_map = {tool.name: tool for tool in self.tools}
        scratchpad = ""

        for _ in range(self.max_steps):
            prompt = self._build_prompt(query, scratchpad)
            plan = complete(prompt)
            thought, action, action_input = _parse_plan(plan)
            if action == "final":
                return action_input, tuple(steps)
            observation = self._execute_action(tool_map, action, action_input)

            step = ReActStep(
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
            )
            steps.append(step)
            scratchpad += (
                f"Thought: {step.thought}\n"
                f"Action: {step.action}\n"
                f"Action Input: {step.action_input}\n"
                f"Observation: {step.observation}\n"
            )

        final = complete(
            "Provide a concise final answer using this reasoning trace.\n\n"
            f"Query: {query}\n\nTrace:\n{scratchpad}"
        )
        return final, tuple(steps)

    def _build_prompt(self, query: str, scratchpad: str) -> str:
        tool_spec = "\n".join(f"- {tool.name}: {tool.description}" for tool in self.tools)
        return (
            "You are a ReAct agent.\n"
            "Return exactly 3 lines:\n"
            "Thought: <brief>\n"
            "Action: <tool_name|final>\n"
            "Action Input: <input or final answer>\n\n"
            f"Tools:\n{tool_spec}\n\n"
            f"User Query: {query}\n\n"
            f"Previous Steps:\n{scratchpad}"
        )


def _parse_plan(plan: str) -> tuple[str, str, str]:
    thought = ""
    action = "final"
    action_input = plan.strip()
    for line in plan.splitlines():
        if line.lower().startswith("thought:"):
            thought = line.split(":", 1)[1].strip()
        elif line.lower().startswith("action:"):
            action = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("action input:"):
            action_input = line.split(":", 1)[1].strip()
    return thought, action, action_input
