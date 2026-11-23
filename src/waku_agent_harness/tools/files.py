"""Helpers shared by the file tools: the project sandbox, text I/O and diffs."""

import difflib
from pathlib import Path

MAX_DIFF_LINES = 80  # longer diffs are cut in the approval prompt


def project_path(path: str, for_writing: bool = False) -> Path:
    """Resolve `path` inside the current project directory. Raises ValueError if it escapes.

    Symlinks are resolved first, so a link pointing outside the project is rejected too.
    Writes into .git are refused as well (a bad write there can corrupt the repository).
    """
    root = Path.cwd().resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("path is outside the project directory")
    if for_writing and ".git" in target.relative_to(root).parts:
        raise ValueError("refusing to touch files inside .git")
    return target


def read_text(target: Path) -> str:
    """Read UTF-8 text exactly as stored (newline="" keeps \\r\\n line endings intact)."""
    with target.open(encoding="utf-8", newline="") as file:
        return file.read()


def write_text(target: Path, content: str) -> None:
    """Write UTF-8 text without translating line endings."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as file:
        file.write(content)


def make_diff(path: str, old: str, new: str) -> str:
    """A unified diff of old -> new for the approval prompt, cut at MAX_DIFF_LINES."""
    lines = list(
        difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
    )
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"… {len(lines) - MAX_DIFF_LINES} more diff lines"]
    return "\n".join(lines)
