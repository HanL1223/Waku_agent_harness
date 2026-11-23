"""Skills: task-specific instructions the agent loads only when it needs them.

A skill is a folder containing a SKILL.md file, optionally with helper scripts:

    .agents/skills/python-lint/
    ├── SKILL.md            <- frontmatter (name, description) + instructions
    └── scripts/lint.py     <- a CLI the instructions tell the agent to run

How the harness uses them ("progressive disclosure"):
  1. At startup only each skill's name + description are read (cheap).
  2. skills_prompt() lists them in the system prompt, so the model knows they exist.
  3. When a request matches, the model calls the `read_skill` tool and gets the full
     SKILL.md, then follows it using its other tools (bash, read_file).
This keeps the system prompt small no matter how many skills are installed.
"""

import sys
from pathlib import Path

import yaml

# Searched in order; if two folders have a skill with the same name, the first one wins,
# so a project skill overrides a personal one.
SKILL_DIRS = [
    Path.cwd() / ".agents" / "skills",  # project skills (checked into the repo)
    Path.home() / "waku_agent_harness" / "skills",  # personal skills (all projects)
]

READ_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "read_skill",
        "description": "Load a skill's full instructions by name. Use it when a listed skill matches the task.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name from the skills list."}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}


def parse_skill(path: Path) -> dict:
    """Read a SKILL.md's frontmatter. Raises ValueError if it is malformed.

    Expected format:
        ---
        name: my-skill
        description: What it does and when to use it.
        ---
        Instructions...
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("file must start with '---' frontmatter")
    parts = text.split("---", 2)  # ["", frontmatter, body]
    if len(parts) < 3:
        raise ValueError("frontmatter is missing its closing '---'")
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    for field in ("name", "description"):
        if not isinstance(meta.get(field), str) or not meta[field].strip():
            raise ValueError(f"frontmatter needs a text '{field}'")
    # Collapse multi-line YAML descriptions into one line for the prompt.
    return {"name": meta["name"].strip(), "description": " ".join(meta["description"].split()), "path": path}


def find_skills() -> dict:
    """Map each skill name to its description and SKILL.md path.

    A broken skill is skipped with a warning (on stderr) instead of crashing the agent.
    """
    skills = {}
    for directory in SKILL_DIRS:
        for path in sorted(directory.glob("*/SKILL.md")):  # a missing directory just yields nothing
            try:
                skill = parse_skill(path)
            except (OSError, ValueError, yaml.YAMLError) as error:
                print(f"warning: skipping skill {path}: {error}", file=sys.stderr)
                continue
            skills.setdefault(skill["name"], skill)  # first one found wins
    return skills


SKILLS = find_skills()  # found once, when the module is first imported


def skills_prompt() -> str:
    """The system-prompt section listing available skills ("" when there are none)."""
    if not SKILLS:
        return ""
    listing = "\n".join(f"- {name}: {skill['description']}" for name, skill in SKILLS.items())
    return (
        "You have skills available; each one is a set of instructions for a kind of task.\n"
        "If a skill matches what the user wants, call read_skill first and follow its instructions.\n\n"
        f"Available skills:\n{listing}"
    )


def read_skill(name: str) -> str:
    """Return a skill's full instructions, headed by its folder so relative paths can be resolved."""
    skill = SKILLS.get(name)
    if skill is None:
        return f"No skill named '{name}'. Available: {', '.join(SKILLS) or 'none'}."
    try:
        body = skill["path"].read_text(encoding="utf-8")
    except OSError as error:
        return f"Error reading skill '{name}': {error}"
    folder = skill["path"].parent
    return f"Skill folder: {folder}\n(Paths like scripts/... in these instructions are relative to it.)\n\n{body}"
