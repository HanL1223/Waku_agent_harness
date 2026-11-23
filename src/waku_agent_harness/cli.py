"""Command-line frontend for the agent.

Designed "CLI-first" (https://agentic-patterns.com/patterns/cli-first-skill-design):
the same command works for a person at a terminal and for scripts or other agents.

    waku                       start an interactive chat (same as `waku chat`)
    waku ask "what is this?"   answer one question and exit
    echo "question" | waku ask read the question from stdin
    waku tools                 list the tools the agent can use
    waku --help                help for everything

Design rules followed here (from the pattern):
  * Subcommands for operations: chat / ask / tools.
  * Readable output on a terminal, JSON when piped: `waku ask ... | jq .answer`.
    Detected with `sys.stdout.isatty()`; force JSON with --json.
  * stdout carries data, stderr carries errors.
  * Exit codes: 0 success, 1 error, 2 bad usage (argparse does this), 130 Ctrl-C.
  * Non-interactive friendly: --yes approves shell commands without asking.
  * Config from the environment (.env): OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL.

How it fits together: `agent.run_turn()` does the work and calls methods on a UI
object as things happen. This file defines two UIs:
  * RichUI - pretty, streamed terminal output (uses the `rich` library).
  * JsonUI - prints nothing while working; records the steps for the final JSON.
"""

import argparse
import json
import os
import sys

import openai
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from waku_agent_harness.agent.agent import TOOLS, AgentUI, new_conversation, run_turn

REQUIRED_ENV = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL")
PREVIEW_LINES = 8  # how many lines of each tool result to show on screen

# Exit codes (see module docstring).
EXIT_OK, EXIT_ERROR, EXIT_INTERRUPTED = 0, 1, 130

console = Console()  # stdout: answers and progress
errors = Console(stderr=True)  # stderr: error messages only


# --------------------------------------------------------------------------- UIs


class RichUI(AgentUI):
    """Shows the agent working: streamed thinking, tool calls, results, and the answer.

    Note: model and tool output is always printed as `Text` (or with markup=False),
    never as rich markup, so text like "[project]" is shown as-is instead of being
    interpreted as a style tag.
    """

    def __init__(self, auto_approve: bool) -> None:
        self.auto_approve = auto_approve
        self.streaming = None  # "reasoning" or "text" while a stream is being printed

    def _stream(self, kind: str, chunk: str, style: str) -> None:
        # Print a blank line when switching between thinking and answer text.
        if self.streaming != kind:
            if self.streaming:
                console.print()
            console.print()
            self.streaming = kind
        console.print(Text(chunk, style=style), end="")

    def reasoning(self, text: str) -> None:
        self._stream("reasoning", text, "dim italic")

    def text(self, text: str) -> None:
        self._stream("text", text, "")

    def message_done(self) -> None:
        if self.streaming:
            console.print()  # finish the streamed line
        self.streaming = None

    def tool_call(self, name: str, arguments: str) -> None:
        console.print()
        console.print(Text.assemble(("● ", "cyan"), (name, "bold cyan"), "  ", summarize_arguments(arguments)))

    def tool_result(self, name: str, result: str) -> None:
        lines = result.splitlines() or ["(no output)"]
        shown = "\n".join(lines[:PREVIEW_LINES])
        if len(lines) > PREVIEW_LINES:
            shown += f"\n… {len(lines) - PREVIEW_LINES} more lines"
        # "└ " then the preview, indented under the tool call.
        console.print(Text("  └ ", style="dim") + Text(shown.replace("\n", "\n    "), style="dim"))

    def approve(self, command: str) -> bool:
        if self.auto_approve:
            console.print(Text("  (auto-approved with --yes)", style="yellow"))
            return True
        console.print(Panel(Text(command), title="Run this command?", border_style="yellow", expand=False))
        try:
            return Confirm.ask("Approve", default=False, console=console)
        except EOFError:  # stdin is not a terminal, so nobody can answer
            return False


class JsonUI(AgentUI):
    """Silent while working; collects each tool step for the JSON output."""

    def __init__(self, auto_approve: bool) -> None:
        self.auto_approve = auto_approve
        self.steps = []

    def tool_call(self, name: str, arguments: str) -> None:
        try:
            parsed = json.loads(arguments)
        except ValueError:
            parsed = arguments  # keep the raw string if the model sent bad JSON
        self.steps.append({"tool": name, "arguments": parsed})

    def tool_result(self, name: str, result: str) -> None:
        self.steps[-1]["result"] = result

    def approve(self, command: str) -> bool:
        # Can't prompt in JSON mode: only --yes allows commands that need approval.
        return self.auto_approve


def summarize_arguments(arguments: str) -> str:
    """Show `{"command": "ls -la"}` as just `ls -la` (our tools take one argument)."""
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return arguments
    if isinstance(parsed, dict) and len(parsed) == 1:
        return str(next(iter(parsed.values())))
    return arguments


# --------------------------------------------------------------------------- commands


def cmd_ask(args) -> int:
    """`waku ask`: answer a single question, then exit."""
    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()  # allow: echo "question" | waku ask
    if not prompt:
        errors.print("error: no question given. Usage: waku ask \"your question\"")
        return 2

    use_json = args.json or not sys.stdout.isatty()
    ui = JsonUI(args.yes) if use_json else RichUI(args.yes)
    answer = run_turn(new_conversation(), prompt, ui)  # errors are handled in main()

    if use_json:
        print(json.dumps({"answer": answer, "steps": ui.steps}, indent=2))
    return EXIT_OK


def cmd_chat(args) -> int:
    """`waku chat`: interactive conversation that remembers earlier turns."""
    if not sys.stdin.isatty():
        errors.print("error: chat needs a terminal. For scripts use: waku ask \"...\"")
        return 2

    console.print(
        Panel.fit(
            f"[bold]waku agent[/]  ·  model [cyan]{escape(os.environ['OPENAI_MODEL'])}[/]\n"
            "[dim]/clear new conversation  ·  /exit or Ctrl-D to quit  ·  Ctrl-C stops the current answer[/]",
            border_style="cyan",
        )
    )
    ui = RichUI(args.yes)
    session = PromptSession()  # gives line editing and ↑/↓ history for free
    messages = new_conversation()

    while True:
        try:
            user_input = session.prompt("\n› ").strip()
        except KeyboardInterrupt:  # Ctrl-C at the prompt: clear the line, keep going
            continue
        except EOFError:  # Ctrl-D: quit
            return EXIT_OK

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            return EXIT_OK
        if user_input == "/clear":
            messages = new_conversation()
            console.print(Text("Conversation cleared.", style="dim"))
            continue

        # Remember where this turn starts. If it fails halfway, drop its partial
        # messages: a tool call without its result would make the next request fail.
        checkpoint = len(messages)
        try:
            run_turn(messages, user_input, ui)
        except KeyboardInterrupt:
            del messages[checkpoint:]
            ui.message_done()
            console.print(Text("\nStopped.", style="yellow"))
        except openai.OpenAIError as error:
            del messages[checkpoint:]
            ui.message_done()
            errors.print(Text(f"API error: {error}", style="red"))


def cmd_tools(args) -> int:
    """`waku tools`: list the tools the agent can call."""
    tools = [{"name": t["function"]["name"], "description": t["function"]["description"]} for t in TOOLS]
    if args.json or not sys.stdout.isatty():
        print(json.dumps(tools, indent=2))
        return EXIT_OK
    table = Table("Tool", "Description", title="Agent tools")
    for tool in tools:
        table.add_row(tool["name"], tool["description"])
    console.print(table)
    return EXIT_OK


# --------------------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    # Options shared by every subcommand, so `waku ask --yes ...` works.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="output JSON (default when stdout is piped)")
    common.add_argument("-y", "--yes", action="store_true", help="approve shell commands without asking")

    # The shared options live on the subcommands only. (If they were also on the top-level
    # parser, argparse would reset them to the subcommand's default: `waku --yes ask` would lose --yes.)
    parser = argparse.ArgumentParser(
        prog="waku",
        description="A small coding agent for your terminal. Runs `chat` when no command is given.",
    )
    parser.set_defaults(func=cmd_chat, json=False, yes=False)  # used when no subcommand is given
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    ask = sub.add_parser("ask", parents=[common], help="answer one question and exit")
    ask.add_argument("prompt", nargs="*", help="the question (or pipe it in on stdin)")
    ask.set_defaults(func=cmd_ask)

    chat = sub.add_parser("chat", parents=[common], help="interactive conversation (default)")
    chat.set_defaults(func=cmd_chat)

    tools = sub.add_parser("tools", parents=[common], help="list the agent's tools")
    tools.set_defaults(func=cmd_tools)
    return parser


def main() -> None:
    args = build_parser().parse_args()  # exits with code 2 on bad usage
    func = args.func

    load_dotenv()
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing and func is not cmd_tools:  # `tools` works without an API
        errors.print(f"error: missing environment variables: {', '.join(missing)} (set them in .env)")
        sys.exit(EXIT_ERROR)

    try:
        sys.exit(func(args))
    except KeyboardInterrupt:
        errors.print("\ninterrupted")
        sys.exit(EXIT_INTERRUPTED)
    except openai.OpenAIError as error:
        errors.print(Text(f"API error: {error}", style="red"))
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
