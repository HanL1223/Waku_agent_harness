---
name: python-lint
description: >
  Lint, format, and review the style of Python code in this project with ruff.
  Use when the user asks to lint, format, tidy, clean up, or check the style or code quality of Python files.
---

# Python lint & style

The linter is a CLI at `scripts/lint.py` in this skill's folder. Run it from the project root with
`uv run python <skill folder>/scripts/lint.py ...`. Its output is JSON when you run it, and the exit code
tells you the result: 0 clean, 1 problems remain, 2 bad usage, 127 ruff missing (tell the user to run `uv sync`).

## Steps

1. **Check first, change nothing.**
   `uv run python <skill folder>/scripts/lint.py check [PATHS]` (default path `.`).
   JSON fields: `clean`, `lint_issues` (file, line, code, message, fixable), `unformatted_files`.
2. **If clean**, say so and stop.
3. **Otherwise, summarize for the user before changing anything**: group issues by file, say how many are
   auto-fixable, and list the files that need formatting. Ask whether to fix them.
4. **Auto-fix** (writes files, so the user will be asked to approve):
   `uv run python <skill folder>/scripts/lint.py fix [PATHS]`. This applies ruff's safe fixes and
   formats, then reports what is left.
5. **Remaining issues need a manual fix.** Read the file with `read_file`, explain the problem and the change
   you propose, and only edit with the user's approval. If a rule seems wrong for this code, say so rather
   than contorting the code. Then run `check` again to confirm.

## Rules in use

Configured in `pyproject.toml` under `[tool.ruff]`: line length 120; rule sets `E`/`F` (errors, real bugs),
`I` (import order), `UP` (modern Python syntax), `B` (likely bugs). Look up an unfamiliar code with
`uv run ruff rule <CODE>`.

## Project style beyond what ruff checks

When reviewing code by hand, also point out departures from the conventions this codebase follows:

- Module docstring at the top explaining what the file is for; docstrings on public functions.
- Type hints on function parameters and return values.
- Tools return errors as strings (`"Error: ..."`) instead of raising, so the agent loop never crashes.
- Comments explain *why*, not *what*.
- No unused imports, variables, or dead code; prefer simple code over clever code.

Report these as suggestions. Only change them if the user asks.
