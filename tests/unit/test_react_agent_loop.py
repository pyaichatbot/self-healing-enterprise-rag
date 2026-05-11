from dataclasses import dataclass

from shrag.agent import react
from shrag.agent.react import ReActAgent, ToolResult


@dataclass(slots=True)
class EchoTool:
    name: str = "echo"
    description: str = "Echo input"

    def run(self, tool_input: str) -> ToolResult:
        return ToolResult(output=f"echo:{tool_input}")


@dataclass(slots=True)
class ExplodeTool:
    name: str = "explode"
    description: str = "Always errors"

    def run(self, tool_input: str) -> ToolResult:
        _ = tool_input
        raise RuntimeError("boom")


def test_parse_plan_handles_structured_response():
    thought, action, action_input = react._parse_plan(
        "Thought: reason\nAction: ECHO\nAction Input: hello"
    )
    assert thought == "reason"
    assert action == "echo"
    assert action_input == "hello"


def test_react_agent_handles_unknown_tool_then_final(monkeypatch):
    calls = iter([
        "Thought: use tool\nAction: missing\nAction Input: x",
        "Thought: conclude\nAction: final\nAction Input: done",
    ])
    monkeypatch.setattr(react, "complete", lambda prompt, **_: next(calls))

    answer, steps = ReActAgent(tools=(EchoTool(),), max_steps=3).run("question")

    assert answer == "done"
    assert len(steps) == 1
    assert steps[0].observation.startswith("Unknown tool:")


def test_react_agent_catches_tool_error(monkeypatch):
    calls = iter([
        "Thought: use tool\nAction: explode\nAction Input: x",
        "Thought: conclude\nAction: final\nAction Input: safe",
    ])
    monkeypatch.setattr(react, "complete", lambda prompt, **_: next(calls))

    answer, steps = ReActAgent(tools=(ExplodeTool(),), max_steps=3).run("question")

    assert answer == "safe"
    assert "Tool error:" in steps[0].observation


def test_react_agent_uses_fallback_summary_after_max_steps(monkeypatch):
    calls = iter([
        "Thought: t1\nAction: echo\nAction Input: a",
        "Thought: t2\nAction: echo\nAction Input: b",
        "final-summary",
    ])
    monkeypatch.setattr(react, "complete", lambda prompt, **_: next(calls))

    answer, steps = ReActAgent(tools=(EchoTool(),), max_steps=2).run("question")

    assert answer == "final-summary"
    assert len(steps) == 2
