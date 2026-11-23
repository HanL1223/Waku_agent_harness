"""The agent loop: send the conversation to the LLM and run the tools it asks for.

This module has no display code. It reports what is happening through an `AgentUI`
object, so any frontend (the rich CLI, JSON output, a future web UI) can show it its own way.
See `waku_agent_harness/cli.py` for the frontend.

One "turn" looks like this:

    user message -> LLM -> (tool calls -> tool results -> LLM)* -> final answer
"""

import json

from waku_agent_harness.llm import SYSTEM_PROMPT, call_llm
from waku_agent_harness.skills.skills import READ_SKILL_TOOL, read_skill, skills_prompt
from waku_agent_harness.tools.bash import BASH_TOOL, run_bash
from waku_agent_harness.tools.read_file import READ_FILE_TOOL, read_file
from waku_agent_harness.tools.str_replace import STR_REPLACE_TOOL, str_replace
from waku_agent_harness.tools.write_file import WRITE_FILE_TOOL, write_file

TOOLS = [BASH_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL, STR_REPLACE_TOOL, READ_SKILL_TOOL]

# Each tool's string arguments (names from its JSON schema), in the order its function takes them.
TOOL_ARGS = {
    "bash": ("command",),
    "read_file": ("path",),
    "write_file": ("path", "content"),
    "str_replace": ("path", "old_str", "new_str"),
    "read_skill": ("name",),
}


class AgentUI:
    """Hooks the loop calls while it works. Override the ones you care about.

    The defaults do nothing and deny every command that needs approval,
    which is the safe behaviour when nobody is watching.
    """

    def reasoning(self, text: str) -> None:
        """A chunk of the model's reasoning (only some providers send this)."""

    def text(self, text: str) -> None:
        """A chunk of the model's reply text, streamed as it arrives."""

    def message_done(self) -> None:
        """The model finished one message (before any tool calls in it run)."""

    def tool_call(self, name: str, arguments: str) -> None:
        """A tool is about to run. `arguments` is the raw JSON string from the model."""

    def tool_result(self, name: str, result: str) -> None:
        """A tool finished; `result` is exactly what the model will see."""

    def approve(self, request: str, title: str = "Run this command?") -> bool:
        """Asked before a risky action: a shell command that is not read-only (`request` is the
        command) or a file change (`request` is a unified diff, `title` names the file).
        Return True to allow it."""
        return False


def new_conversation() -> list:
    """A fresh message list containing only the system prompt (plus the list of skills, if any)."""
    system = SYSTEM_PROMPT
    if skills := skills_prompt():
        system += "\n" + skills
    return [{"role": "system", "content": system}]


def run_tool(call, approve) -> str:
    """Execute one tool call and return its result as a string.

    Mistakes by the model (bad JSON, unknown tool, wrong argument type) are returned
    as text instead of raised, so the model can read the error and try again.
    """
    try:
        name = call.function.name
        if call.type != "function" or name not in TOOL_ARGS:
            raise ValueError("Unknown tool")
        arguments = json.loads(call.function.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Expected an object of arguments")
        values = []
        for arg in TOOL_ARGS[name]:
            if not isinstance(arguments.get(arg), str):
                raise ValueError(f"Expected a string {arg}")
            values.append(arguments[arg])
    except (ValueError, TypeError) as error:
        return f"Invalid tool request: {error}"

    if name == "bash":
        return run_bash(*values, approve=approve)
    if name == "write_file":
        return write_file(*values, approve=approve)
    if name == "str_replace":
        return str_replace(*values, approve=approve)
    if name == "read_skill":
        return read_skill(*values)
    return read_file(*values)


def run_turn(messages: list, user_input: str, ui: AgentUI) -> str:
    """Answer one user message, running tools as needed. Returns the final answer.

    `messages` is updated in place, so passing the same list again continues the
    conversation (this is how the CLI's chat mode remembers earlier turns).
    """
    messages.append({"role": "user", "content": user_input})
    while True:
        # Stream the reply: text and reasoning reach the UI chunk by chunk.
        message = call_llm(messages, TOOLS, on_text=ui.text, on_reasoning=ui.reasoning)
        ui.message_done()
        # The assistant message must be in the history before its tool results.
        messages.append(message.model_dump(exclude_unset=True))

        if not message.tool_calls:  # no tools requested -> this is the final answer
            return message.content or ""

        for call in message.tool_calls:
            ui.tool_call(call.function.name, call.function.arguments)
            result = run_tool(call, approve=ui.approve)
            ui.tool_result(call.function.name, result)
            # Each result is linked to its request by tool_call_id.
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
