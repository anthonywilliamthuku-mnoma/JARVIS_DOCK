# Skills catalog

Status values: `planned` (no code), `stub` (manifest and SKILL.md only), `working` (implemented), `tested` (implemented with passing tests).

Tiers follow the master spec, section 5: T0 observe, T1 act (reversible), T2 sensitive, T3 admin, T4 never.

Backlog and priorities live in `SKILLS_BACKLOG.md`. The catalog is empty until Phase 2 adds the skill framework.

| Skill | Priority | Status | Max tier | Requires admin | Tests |
|---|---|---|---|---|---|
| (none yet) | | | | | |

## Adding a skill

Use the scaffold once it exists (`leon skill new <name>`, Phase 2). A skill lives in `skills/<name>/` with `SKILL.md`, `manifest.yaml`, `tools/`, `tests/` and `examples/`. Add its row here when it is created.
