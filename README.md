# Personal workflow skills

A collection of reusable skills for my own workflows, following the portable
[Agent Skills format](https://agentskills.io/specification).

## Layout

```text
skills/<skill-name>/
  SKILL.md             Required metadata and instructions
  scripts/             Optional executable helpers
  references/          Optional supporting documentation
  assets/              Optional files used in generated output
```

Each immediate directory inside `skills/` is one skill. Keep its name lowercase,
using letters, digits, and single hyphens. The name in its frontmatter must match
the directory name. Create supporting directories only when the workflow needs
them. Agent-specific files, such as `agents/openai.yaml`, are optional.

## Add a skill

Create `skills/<skill-name>/SKILL.md` with YAML frontmatter and useful Markdown
instructions. For example, a future `summarize-notes` skill could start with:

```markdown
---
name: summarize-notes
description: Turn meeting notes into decisions and action items when asked to summarize a meeting.
---

Extract decisions and action items from the supplied notes. Include owners and
due dates when present; flag missing details instead of inventing them.
```

Describe both the capability and when it applies. Keep instructions focused on
the workflow's useful context and constraints. Link supporting resources using
relative paths within the skill, and keep each skill self-contained.

Standard optional frontmatter fields are `license`, `compatibility`, `metadata`,
and `allowed-tools`. Put custom properties in `metadata` as string keys and
string values. Environment requirements belong in `compatibility`; individual
skills may use any appropriate tools.

## Development

Repository validation uses Python 3.12 or newer. From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

To validate selected skills, pass one or more directory paths:

```sh
python scripts/validate_skills.py skills/summarize-notes
```

With no arguments, the validator checks every immediate directory in the
repository's `skills/` collection. An empty collection passes; a missing
collection fails. Explicit relative paths resolve from your current directory.
Failures include their paths and produce a nonzero exit status.

Validation checks frontmatter structure, standard fields, naming, and length
limits. This repository also requires nonempty Markdown instructions. Validation
does not judge instruction quality, execute skill helpers, or require particular
headings or agent metadata. Review the skill against realistic requests and
verify any executable helpers separately.

GitHub Actions runs the same validation and tests on pushes and pull requests.
