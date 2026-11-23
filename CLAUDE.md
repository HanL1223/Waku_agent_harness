# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A minimal coding-agent harness: an LLM loop (via the OpenAI-compatible Chat Completions API) that can call local tools (`bash`, `read_file`). Python ≥3.10, managed with `uv` (`uv_build` backend, src layout).

## Commands

```bash
uv sync                                      # install deps into .venv
uv run waku                                  # interactive chat (main entry point; = `waku chat`)
uv run waku ask "question"                   # one-shot; JSON on stdout when piped or with --json
uv run waku tools                            # list tools
uv run python -m waku_agent_harness.llm      # older standalone loop (no streaming, no CLI)
```

`waku` options: `--json`, `-y/--yes` (auto-approve non-read-only shell commands). Exit codes: 0 ok, 1 error, 2 usage, 130 Ctrl-C. When testing `waku ask` from a non-TTY shell, pass the question or redirect `</dev/null`, otherwise it blocks reading the question from stdin.

There is no test suite yet. Lint/format with ruff (config in `pyproject.toml`, dev dependency):

```bash
uv run ruff check src && uv run ruff format --check src
uv run python .agents/skills/python-lint/scripts/lint.py check [PATHS]   # same, JSON when piped
```

## Configuration

`.env` (loaded with `python-dotenv`) must define `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Any OpenAI-compatible endpoint works; the model is not hard-coded.

## Architecture

- `llm/__main__.py` — the agent loop. Reads one prompt from stdin, then repeatedly calls `chat.completions.create` with all tool schemas; appends the assistant message and one `role: "tool"` message per tool call; exits and prints the reply when the model returns no tool calls. Tool dispatch is an `if/elif` on the function name, with argument validation errors returned to the model as the tool result (`"Invalid tool request: ..."`) rather than raised.
- `tools/` — each module exports a pair: a `*_TOOL` dict (OpenAI function-tool JSON schema, `additionalProperties: False`) and a plain function returning a string. Adding a tool means adding the module, adding it to `TOOLS` and `TOOL_ARGS` in `agent/agent.py`, and a dispatch line in `run_tool`. (`read_skill` lives in `skills/`, not `tools/`, but is registered the same way.)
  - `bash.py` — `is_read_only()` lets commands run without approval only if every piped segment is on an allowlist (`READ_ONLY_COMMANDS`, read-only git subcommands, no write/exec flags from `FORBIDDEN_ARGS`) and the line has no redirection, substitution or chaining characters; when unsure it asks. Everything else calls the `approve` callback (default `ask_in_terminal`, a `[y/N]` prompt) (`shell=True`, 600s timeout, `TIMEOUT_SECONDS`); a denial is returned to the model as `"Command denied by user."`, and the system prompt tells the model not to retry denied commands.
  - `read_file.py` — sandboxed to `Path.cwd()` (rejects paths that resolve outside it), caps reads at 64 KiB with a truncation marker.
- Tools report failures as strings, never exceptions, so the loop always has something to send back to the model.
- `llm/__init__.py` — `SYSTEM_PROMPT` and `call_llm(messages, tools, on_text, on_reasoning)`: streams the completion, forwards text/reasoning chunks to the callbacks, reassembles fragmented tool calls, and returns a `ChatCompletionMessage` (with `reasoning_content` kept as an extra field when the provider sends it).
- `agent/agent.py` — the loop, with no display code. `run_turn(messages, user_input, ui)` mutates `messages` in place (so chat mode reuses the list) and reports progress through an `AgentUI` hooks object (`reasoning`, `text`, `message_done`, `tool_call`, `tool_result`, `approve`). The base class is silent and denies approvals. `run_tool` validates args against `TOOL_ARGS` and passes `ui.approve` to `run_bash`.
- `cli.py` — the `waku` frontend (argparse subcommands, CLI-first design). `RichUI` streams to the terminal; `JsonUI` collects steps for JSON output. Model/tool output is printed as `rich.Text`, never markup, so brackets aren't eaten. Chat rolls `messages` back to a checkpoint when a turn is interrupted or errors, because a dangling tool call breaks the next request.
- `skills/skills.py` — skills are folders with a `SKILL.md` (YAML frontmatter `name` + `description`, then instructions) in `.agents/skills/` (project) or `~/waku_agent_harness/skills/` (personal; project wins on name clashes). Found once at import (`SKILLS`); malformed ones are skipped with a stderr warning. `skills_prompt()` appends the name/description list to the system prompt in `agent.new_conversation()`; the model loads full instructions via the `read_skill` tool, whose result is prefixed with the skill's folder so `scripts/...` paths resolve. Skill scripts run through `bash`, so they need approval (they aren't on the read-only allowlist).
- `.agents/skills/python-lint/` — example skill: `scripts/lint.py check|fix [PATHS]` wraps ruff with JSON output (exit 0 clean, 1 problems, 2 usage, 127 ruff missing). It parses ruff's `--output-format=json` for both check and format, since ruff's text output wording changes between versions.
- `llm/__main__.py` still has its own older copy of the loop.
