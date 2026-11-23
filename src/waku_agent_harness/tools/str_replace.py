"""Edit part of a text file by replacing one exact, unique snippet (asks for approval)."""

from waku_agent_harness.tools.files import make_diff, project_path, read_text, write_text

STR_REPLACE_TOOL = {
    "type": "function",
    "function": {
        "name": "str_replace",
        "description": (
            "Edit an existing text file in the project directory by replacing one exact snippet. "
            "old_str must match the file exactly (including whitespace and indentation) and occur exactly once; "
            "include a few surrounding lines to make it unique. Use an empty new_str to delete the snippet. "
            "Read the file first. Needs user approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the project directory."},
                "old_str": {"type": "string", "description": "Exact text to find; must occur exactly once."},
                "new_str": {"type": "string", "description": "Replacement text (may be empty)."},
            },
            "required": ["path", "old_str", "new_str"],
            "additionalProperties": False,
        },
    },
}


def str_replace(path: str, old_str: str, new_str: str, approve) -> str:
    """Replace the single occurrence of `old_str` with `new_str` after approval."""
    if not old_str:
        return "Error: old_str is empty. To create a file or replace all of it, use write_file."
    if old_str == new_str:
        return "Error: old_str and new_str are identical, so there is nothing to change."
    try:
        target = project_path(path, for_writing=True)
        if not target.is_file():
            return f"Error: {path} does not exist or is not a file. To create it, use write_file."
        old = read_text(target)

        count = old.count(old_str)
        if count == 0:
            return (
                f"Error: old_str was not found in {path}. It must match exactly, including whitespace "
                "and indentation. Read the file again and copy the text from it."
            )
        if count > 1:
            return f"Error: old_str occurs {count} times in {path}. Include more surrounding lines so it is unique."

        start = old.index(old_str)
        new = old[:start] + new_str + old[start + len(old_str) :]
        if not approve(make_diff(path, old, new), f"Edit {path}?"):
            return "Edit denied by user."
        write_text(target, new)
    except (OSError, ValueError, UnicodeError, RuntimeError) as error:
        return f"Error editing file: {error}"
    first = old.count("\n", 0, start) + 1
    if not new_str:
        return f"Edited {path}: deleted the snippet at line {first}."
    last = first + new_str.count("\n")
    return f"Edited {path}: replaced 1 occurrence (now lines {first}-{last})."
