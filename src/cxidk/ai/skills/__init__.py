"""Bundled Agent Skills (`SKILL.md`) for CCAI Insights workflows."""

from pathlib import Path
from typing import List

from cxidk.core import errors

_SKILLS_DIR = Path(__file__).resolve().parent


def list_skills() -> List[str]:
    """Lists bundled Agent Skill directory names.

    Returns:
        Sorted list of available skill names.
    """
    return sorted(
        entry.name
        for entry in _SKILLS_DIR.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    )


def get_skill_path(name: str) -> Path:
    """Resolves the filesystem path to `SKILL.md` for a bundled skill.

    Args:
        name: Skill directory name (for example, `'cx-insights-analyst'`).

    Returns:
        Validated `Path` pointing to the skill's `SKILL.md`.

    Raises:
        InvalidArgumentError: If `name` contains path separators or traversal.
        NotFoundError: If no bundled skill matches `name`.
    """
    clean = name.strip()
    if "/" in clean or "\\" in clean or ".." in clean:
        raise errors.InvalidArgumentError(f"Invalid skill name: {name!r}")
    skill_md = _SKILLS_DIR / clean / "SKILL.md"
    if not skill_md.is_file():
        raise errors.NotFoundError(
            f"Unknown skill {name!r}.",
            hint=f"Available skills: {list_skills()}",
        )
    return skill_md


def load_skill(name: str) -> str:
    """Reads and returns the full Markdown contents of `SKILL.md` for `name`.

    Args:
        name: Skill directory name.

    Returns:
        UTF-8 Markdown string of the requested `SKILL.md`.

    Raises:
        InvalidArgumentError: If `name` contains path separators or traversal.
        NotFoundError: If no bundled skill matches `name`.
    """
    return get_skill_path(name).read_text(encoding="utf-8")


__all__ = ["get_skill_path", "list_skills", "load_skill"]
