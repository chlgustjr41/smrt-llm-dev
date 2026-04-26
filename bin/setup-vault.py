#!/usr/bin/env python3
"""
Initialize an Obsidian vault skeleton in a project's wiki/ directory.

Usage:
    python bin/setup-vault.py <project-path>

Creates:
    wiki/index.md              Master catalog with wikilinks template
    wiki/hot.md                Recent-context cache
    wiki/log.md                Append-only operation log
    wiki/_moc/api-reference.md Map of content for API endpoints
    wiki/_moc/modules.md       Map of content for modules
    wiki/_moc/recent-changes.md Auto-gen from git log placeholder
    wiki/_moc/security.md      Security-relevant code paths MOC
    wiki/meta/dashboard.base   Obsidian Bases dashboard JSON

Each markdown file includes minimal YAML frontmatter with type, tags, and updated date.
Only creates files/directories that don't already exist — never overwrites.
"""

import sys
import json
from datetime import date
from pathlib import Path


FRONTMATTER_TEMPLATE = """\
---
type: {type}
tags: []
updated: {date}
---
"""

INDEX_MD = """# Vault Index

Master catalog of documentation. Use wikilinks to navigate:

- [[hot|Recent Context]] — Today's active notes
- [[log|Operation Log]] — Append-only event log

## Maps of Content

- [[_moc/api-reference|API Reference MOC]]
- [[_moc/modules|Modules MOC]]
- [[_moc/recent-changes|Recent Changes MOC]]
- [[_moc/security|Security MOC]]

## Quick Links

- [GitHub Issues](#)
- [Architecture Docs](#)
- [Deploy Runbooks](#)
"""

HOT_MD = """# Hot (Recent Context)

Active work, current issues, today's focus.

## Today's Focus

- [ ] Task 1
- [ ] Task 2

## Current Issues

(Add blocking issues here)

## Notes

(Ephemeral notes for this work cycle)
"""

LOG_MD = """# Operation Log

Append-only log of significant events, changes, and decisions.

## Format

- `YYYY-MM-DD HH:MM` — Brief description of change or event

## Entries

(Append new entries at the top)
"""

API_REFERENCE_MOC = """# API Reference Map of Content

Index of API endpoints and their implementations.

## Endpoints by Resource

- Users — `/api/users/*`
- Posts — `/api/posts/*`
- Comments — `/api/comments/*`

## Schema Definitions

(Link to relevant Pydantic models and type definitions)
"""

MODULES_MOC = """# Modules Map of Content

Overview of project modules and their responsibilities.

## Core Modules

- `auth` — Authentication and authorization
- `models` — Data models and schemas
- `service` — Business logic layer
- `api` — FastAPI route handlers

## Dependencies

(Diagram or adjacency list of module relationships)
"""

RECENT_CHANGES_MOC = """# Recent Changes Map of Content

Auto-generated from git log (placeholder).

To auto-generate:
```bash
git log --oneline -20
```

## Latest Commits

(Auto-generated placeholder — update manually or via git integration)
"""

SECURITY_MOC = """# Security Map of Content

Security-relevant code paths and vulnerability surface area.

## Authentication & Authorization

(Link to auth-related files)

## Input Validation

(Link to validation schemas and sanitization)

## Database Access

(SQL query construction, injection vectors)

## External APIs & Secrets

(Credential handling, API key management)
"""

DASHBOARD_BASE = {
    "version": 1,
    "filters": [],
    "columns": []
}


def create_file(path: Path, content: str, frontmatter_type: str) -> bool:
    """Create file with frontmatter if it doesn't exist. Return True if created."""
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    frontmatter = FRONTMATTER_TEMPLATE.format(type=frontmatter_type, date=today)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(frontmatter)
        f.write(content)

    return True


def create_json_file(path: Path, data: dict) -> bool:
    """Create JSON file if it doesn't exist. Return True if created."""
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python bin/setup-vault.py <project-path>", file=sys.stderr)
        sys.exit(1)

    project_path = Path(sys.argv[1]).resolve()
    if not project_path.is_dir():
        print(f"Error: Project path not found: {project_path}", file=sys.stderr)
        sys.exit(1)

    wiki_dir = project_path / "wiki"
    moc_dir = wiki_dir / "_moc"
    meta_dir = wiki_dir / "meta"

    created = []
    skipped = []

    # Create markdown files
    files_to_create = [
        (wiki_dir / "index.md", INDEX_MD, "index"),
        (wiki_dir / "hot.md", HOT_MD, "hot"),
        (wiki_dir / "log.md", LOG_MD, "log"),
        (moc_dir / "api-reference.md", API_REFERENCE_MOC, "moc"),
        (moc_dir / "modules.md", MODULES_MOC, "moc"),
        (moc_dir / "recent-changes.md", RECENT_CHANGES_MOC, "moc"),
        (moc_dir / "security.md", SECURITY_MOC, "moc"),
    ]

    for path, content, fm_type in files_to_create:
        if create_file(path, content, fm_type):
            created.append(str(path.relative_to(project_path)))
        else:
            skipped.append(str(path.relative_to(project_path)))

    # Create dashboard.base
    if create_json_file(meta_dir / "dashboard.base", DASHBOARD_BASE):
        created.append(str((meta_dir / "dashboard.base").relative_to(project_path)))
    else:
        skipped.append(str((meta_dir / "dashboard.base").relative_to(project_path)))

    # Print summary
    if created:
        print(f"Created {len(created)} file(s):")
        for path in created:
            print(f"  + {path}")

    if skipped:
        print(f"Skipped {len(skipped)} file(s) (already exist):")
        for path in skipped:
            print(f"  - {path}")

    if not created:
        print("No files created (vault already exists).")

    sys.exit(0)


if __name__ == "__main__":
    main()
