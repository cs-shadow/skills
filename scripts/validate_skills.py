#!/usr/bin/env python3
"""Validate portable skills against https://agentskills.io/specification.

Repository convention: instructions must contain non-whitespace content.
This is a structural check, not a behavioral evaluation of a skill.
"""

import argparse
from pathlib import Path
import re
import sys

import yaml


DEFAULT_COLLECTION = Path(__file__).resolve().parents[1] / "skills"
ALLOWED_FIELDS = {
    "name", "description", "license", "compatibility", "metadata", "allowed-tools"
}


def validate_skill(directory: Path) -> list[str]:
    """Return all detectable structural errors for one skill directory."""
    directory = directory.resolve()
    if not directory.is_dir():
        return ["skill path must be an existing directory"]
    try:
        content = (directory / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"cannot read SKILL.md: {error}"]

    lines = content.splitlines()
    if not lines or lines[0] != "---":
        return ["SKILL.md must start with a YAML frontmatter delimiter (---)"]
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return ["YAML frontmatter is missing its closing delimiter (---)"]

    errors = []
    if not "\n".join(lines[closing + 1:]).strip():
        errors.append("Markdown instructions must not be empty")
    try:
        fields = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as error:
        return errors + [f"invalid YAML frontmatter: {error}"]
    if not isinstance(fields, dict):
        return errors + ["YAML frontmatter must be a mapping"]

    for field in fields:
        if field not in ALLOWED_FIELDS:
            errors.append(f"unknown frontmatter field {field!r}; use metadata for extensions")
    for field in ("name", "description"):
        if field not in fields:
            errors.append(f"missing required field: {field}")
    for field in ("name", "description", "license", "compatibility", "allowed-tools"):
        if field in fields and not isinstance(fields[field], str):
            errors.append(f"{field} must be a string")

    name = fields.get("name")
    if isinstance(name, str):
        if not 1 <= len(name) <= 64:
            errors.append("name must contain 1–64 characters")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append("name must use lowercase letters, digits, and single separating hyphens")
        if name != directory.name:
            errors.append(f"name must match directory name {directory.name!r}")

    for field, limit in (("description", 1024), ("compatibility", 500)):
        value = fields.get(field)
        if isinstance(value, str) and (not value.strip() or len(value) > limit):
            errors.append(f"{field} must contain 1–{limit} characters and not be blank")

    if "metadata" in fields:
        metadata = fields["metadata"]
        if not isinstance(metadata, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in metadata.items()
        ):
            errors.append("metadata must be a mapping of string keys to string values")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories", nargs="*", type=Path,
        help="skill directories (default: every immediate directory in skills/)",
    )
    args = parser.parse_args(argv)
    directories = args.directories
    if not directories:
        if not DEFAULT_COLLECTION.is_dir():
            print(f"{DEFAULT_COLLECTION}: collection directory is missing", file=sys.stderr)
            return 1
        try:
            directories = sorted(path for path in DEFAULT_COLLECTION.iterdir() if path.is_dir())
        except OSError as error:
            print(f"{DEFAULT_COLLECTION}: cannot read collection: {error}", file=sys.stderr)
            return 1
        if not directories:
            print(f"No skills found in {DEFAULT_COLLECTION}; empty collection is valid.")
            return 0

    failed = 0
    for directory in directories:
        errors = validate_skill(directory)
        if errors:
            failed += 1
            for error in errors:
                print(f"{directory}: {error}", file=sys.stderr)
        else:
            print(f"{directory}: valid")
    print(f"Checked {len(directories)} skill(s); {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
