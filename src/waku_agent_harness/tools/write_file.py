"""Create or overwrite a text file within the project directory (asks for approval)."""

from waku_agent_harness.tools.files import make_diff, project_path, read_text, write_text

WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": (
            "Create a new UTF-8 text file, or replace an existing file's entire contents, within the project "
            "directory. Parent folders are created as needed. Needs user approval. "
            "To change part of an existing file, use str_replace instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the project directory."},
                "content": {"type": "string", "description": "The complete new contents of the file."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
}


def write_file(path: str, content: str, approve) -> str:
    """Write `content` to `path` after `approve(description, title)` returns True."""
    try:
        target = project_path(path, for_writing=True)
        if target.is_dir():
            return f"Error: {path} is a directory."
        exists = target.exists()
        old = read_text(target) if exists else ""
        if exists and old == content:
            return f"No change: {path} already has exactly this content."

        title = f"Overwrite {path}?" if exists else f"Create {path}?"
        if not approve(make_diff(path, old, content) or f"(empty file {path})", title):
            return "Write denied by user."
        write_text(target, content)
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        return f"Error writing file: {error}"
    return f"{'Overwrote' if exists else 'Created'} {path} ({len(content.splitlines())} lines)."
