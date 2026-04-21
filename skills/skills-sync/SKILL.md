---
name: skills-sync
description: Sync your AI skills library to Google Shared Drive. Use when updating, adding, or reviewing skills. Governs the full workflow — pull latest, generate D2 diagrams, push changes.
---

# skills-sync

Manages your shared AI skills library. Skills live in `~/.local/share/sync-skills/skills/` and are symlinked to both `~/.claude/skills` and `~/.gemini/skills`.

## Commands

```bash
skills-sync              # incremental push — only files changed since last sync
skills-sync --full       # force push everything
skills-sync --pull       # pull latest from Drive
skills-sync --dry-run    # preview what would be pushed
```

## Workflow — When a skill is updated or created

Always follow this sequence:

**1. Pull first** — check Drive for newer versions before making changes:
```bash
skills-sync --pull
```

**2. Make your changes** to the skill's `SKILL.md`.

**3. Generate the D2 diagram** using the `d2-architect-standard` skill. Create or update `diagram.d2` in the skill's folder to reflect its architecture, components, and data flows. Use the skill's `name:` frontmatter field as the diagram title. Then render:
```bash
d2 -t 0 ~/.local/share/sync-skills/skills/<skill-name>/diagram.d2 \
         ~/.local/share/sync-skills/skills/<skill-name>/diagram.svg
```

**4. Push to Drive:**
```bash
skills-sync
```

## Rules

- **Always pull before editing** a skill to avoid overwriting newer Drive versions.
- **Always push after editing** — never leave a skill updated locally without syncing.
- **Always generate or update the D2 diagram** when a skill's SKILL.md changes.
- Skills dir is the source of truth after a pull; Drive is the source of truth before you start.

## Skills directory

```
~/.local/share/sync-skills/skills/
    <skill-name>/
        SKILL.md       ← skill instructions
        diagram.d2     ← D2 source (auto-generated)
        diagram.svg    ← rendered diagram (auto-generated)
```
