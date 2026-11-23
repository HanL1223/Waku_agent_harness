"""Read text files within the current project directory."""

from waku_agent_harness.tools.files import project_path

MAX_BYTES = 64 * 1024

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file within the project directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to the project directory."}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def read_file(path: str) -> str:
    try:
        target = project_path(path)
        with target.open("rb") as file:
            data = file.read(MAX_BYTES + 1)
        truncated = len(data) > MAX_BYTES
        # Ignore an incomplete final UTF-8 character only when truncating.
        content = data[:MAX_BYTES].decode("utf-8", errors="ignore" if truncated else "strict")
        if truncated:
            content += "\n[File truncated at 64 KiB.]"
        return content
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        return f"Error reading file: {error}"
