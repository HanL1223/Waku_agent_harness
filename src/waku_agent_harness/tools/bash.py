"""A shell tool that asks for approval before running a command."""

import subprocess

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command in the current project directory, with user approval.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to run."}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}


def run_bash(command: str) -> str:
    print(f"\nRequested shell command:\n{command}", flush=True)
    try:
        approved = input("Run this command? [y/N] ").strip().lower() == "y"
    except EOFError:
        approved = False
    if not approved:
        return "Command denied by user."
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except OSError as error:
        return f"Could not run command: {error}"
    return f"Exit code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
