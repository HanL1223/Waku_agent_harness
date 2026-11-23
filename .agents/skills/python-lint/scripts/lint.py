#!/usr/bin/env python3
"""Lint and format Python code with ruff. Works for people and for agents (CLI-first).

Usage (from the project root):
    uv run python .agents/skills/python-lint/scripts/lint.py check [PATH ...]   # report only
    uv run python .agents/skills/python-lint/scripts/lint.py fix   [PATH ...]   # auto-fix + format

PATH defaults to the current directory. Rules come from [tool.ruff] in pyproject.toml.

Output: readable text on a terminal, JSON when piped (or with --json), e.g.
    {"clean": false, "lint_issues": [{"file": ..., "line": 3, "code": "I001", "message": ..., "fixable": true}],
     "unformatted_files": ["src/x.py"]}

Exit codes: 0 clean, 1 problems remain, 2 bad usage, 127 ruff not installed.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys

EXIT_CLEAN, EXIT_PROBLEMS, EXIT_USAGE, EXIT_NOT_FOUND = 0, 1, 2, 127


def ruff(*args: str) -> subprocess.CompletedProcess:
    """Run ruff through the current Python, so the project's installed version is used."""
    return subprocess.run([sys.executable, "-m", "ruff", *args], capture_output=True, text=True)


def lint_issues(paths: list) -> list:
    """Lint problems as simple dicts (ruff's JSON output, trimmed to what matters)."""
    result = ruff("check", "--output-format=json", *paths)
    if result.returncode not in (0, 1):  # 0 = no issues, 1 = issues found, anything else = ruff failed
        raise RuntimeError(result.stderr.strip() or "ruff check failed")
    return [
        {
            "file": os.path.relpath(item["filename"]),  # ruff gives absolute paths; shorten them
            "line": item["location"]["row"],
            "code": item["code"],
            "message": item["message"],
            # True only if `fix` will handle it: ruff applies "safe" fixes by default, not "unsafe" ones.
            "fixable": (item.get("fix") or {}).get("applicability") == "safe",
        }
        for item in json.loads(result.stdout or "[]")
    ]


def unformatted_files(paths: list) -> list:
    """Files `ruff format` would change. `--check` only reports; it never writes."""
    # JSON output is stable across ruff versions (its plain-text wording has changed before).
    result = ruff("format", "--check", "--output-format=json", *paths)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "ruff format failed")
    files = {os.path.relpath(item["filename"]) for item in json.loads(result.stdout or "[]")}
    return sorted(files)


def report(issues: list, unformatted: list, as_json: bool, header: str = "") -> int:
    """Print the results (JSON or text) and return the exit code."""
    clean = not issues and not unformatted
    if as_json:
        print(json.dumps({"clean": clean, "lint_issues": issues, "unformatted_files": unformatted}, indent=2))
        return EXIT_CLEAN if clean else EXIT_PROBLEMS

    if header:
        print(header)
    if clean:
        print("✓ No lint issues; formatting is clean.")
        return EXIT_CLEAN
    for issue in issues:
        mark = " [auto-fixable]" if issue["fixable"] else ""
        print(f"{issue['file']}:{issue['line']}  {issue['code']}  {issue['message']}{mark}")
    for path in unformatted:
        print(f"{path}  needs formatting")
    print(f"\n{len(issues)} lint issue(s), {len(unformatted)} file(s) to format.")
    return EXIT_PROBLEMS


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint and format Python code with ruff.")
    parser.add_argument("command", choices=["check", "fix"], help="check: report only. fix: apply safe fixes + format")
    parser.add_argument("paths", nargs="*", default=["."], help="files or folders (default: .)")
    parser.add_argument("--json", action="store_true", help="JSON output (default when stdout is piped)")
    args = parser.parse_args()  # exits with 2 on bad usage
    as_json = args.json or not sys.stdout.isatty()

    if importlib.util.find_spec("ruff") is None:
        print("error: ruff is not installed. Run: uv sync  (or: uv add --dev ruff)", file=sys.stderr)
        return EXIT_NOT_FOUND

    try:
        if args.command == "fix":
            # Only "safe" fixes (ruff's default); then reformat. Both write files.
            ruff("check", "--fix", *args.paths)
            ruff("format", *args.paths)
        # Report what is left after fixing (or everything, for `check`).
        header = "After fixing, remaining:" if args.command == "fix" else ""
        return report(lint_issues(args.paths), unformatted_files(args.paths), as_json, header)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_PROBLEMS


if __name__ == "__main__":
    sys.exit(main())
