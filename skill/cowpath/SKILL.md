---
name: cowpath
description: Offline historical DSH session reviewer that proposes new or merged workspace Skills and requires human confirmation before writing.
license: MIT
metadata:
  version: "0.2.0"
---

# Cowpath

Run `cowpath --workspace /absolute/path/to/workspace` to inspect historical DSH sessions for that workspace. Cowpath proposes either a new Skill or a merge into an existing `.agents/skills/*/SKILL.md`; every write requires an explicit interactive choice. Use `--proposals-only` for a read-only review.
