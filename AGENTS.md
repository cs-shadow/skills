# AGENTS.md

## Skills

* Store each portable skill in `skills/<skill-name>/SKILL.md`, following the
  [Agent Skills specification](https://agentskills.io/specification).
* Keep instructions focused on useful workflow context and constraints. Make
  descriptions explain the capability and when it should activate.
* Keep skills self-contained and link supporting resources with relative paths.
  Add scripts, references, assets, or agent-specific metadata only when useful.
* Do not add placeholder skills. Keep the collection empty until a real workflow
  is requested.
* Run `python scripts/validate_skills.py` after changing skills. When changing
  repository tooling, also run `python -m unittest discover -s tests -v`.
