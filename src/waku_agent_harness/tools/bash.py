"""A shell tool that runs read-only commands directly and asks for approval for anything else."""

import shlex
import subprocess

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run a shell command in the current project directory. Simple read-only commands "
            "(ls, cat, grep, git status/log/diff, ...) run immediately; anything else needs user approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to run."}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}

# Commands that only read. Anything not listed here (including commands that can write
# via a flag or script, like sed -i, awk, sort -o, tee, env, xargs) needs approval.
READ_ONLY_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep", "rg", "pwd", "echo", "file", "stat",
    "du", "df", "which", "whoami", "date", "uname", "cut", "tr", "diff", "basename",
    "dirname", "realpath", "find", "git",
}
READ_ONLY_GIT_SUBCOMMANDS = {"status", "log", "diff", "show", "ls-files", "blame", "rev-parse"}
# Flags that make an otherwise read-only command write files or run other programs.
FORBIDDEN_ARGS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "rg": ("--pre",),
    "git": ("--output", "--ext-diff", "--textconv"),
}
TIMEOUT_SECONDS = 600  # long enough for browser automation (ego-browser) scripts
# Characters that enable redirection, substitution, chaining or hidden extra lines.
UNSAFE_CHARS = set(";&<>`$()\n\r")


def is_read_only(command: str) -> bool:
    """Return True only if every command in a (possibly piped) command line is known read-only."""
    if not command.strip() or UNSAFE_CHARS & set(command):
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False

    segments, current = [], []
    for token in tokens:
        if token == "|":
            segments.append(current)
            current = []
        elif set(token) == {"|"}:  # "||"
            return False
        else:
            current.append(token)
    segments.append(current)

    for argv in segments:
        if not argv or argv[0] not in READ_ONLY_COMMANDS:
            return False
        name, args = argv[0], argv[1:]
        if name == "git" and (not args or args[0] not in READ_ONLY_GIT_SUBCOMMANDS):
            return False
        if any(arg.startswith(flag) for arg in args for flag in FORBIDDEN_ARGS.get(name, ())):
            return False
    return True


def ask_in_terminal(command: str) -> bool:
    """Default approver: show the command and ask y/N on the terminal."""
    print(f"\nRequested shell command:\n{command}", flush=True)
    try:
        return input("Run this command? [y/N] ").strip().lower() == "y"
    except EOFError:  # no terminal to ask (e.g. input is piped) -> treat as "no"
        return False


def run_bash(command: str, approve=ask_in_terminal) -> str:
    """Run a shell command. Read-only commands run directly; others need approve(command) to be True.

    `approve` is a function so different frontends can ask in their own way (the CLI passes its own).
    """
    if not is_read_only(command) and not approve(command):
        return "Command denied by user."
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {TIMEOUT_SECONDS} seconds."
    except OSError as error:
        return f"Could not run command: {error}"
    return f"Exit code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
