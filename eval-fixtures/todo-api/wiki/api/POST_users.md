---
type: endpoint
tags: []
updated: 2026-04-25
---

# POST /users

**Authentication:** None

**Purpose:** Create a user from `{email, password}`; returns `UserOut` (id, email). Stores `password_hash` server-side as the literal string `f"hashed:{password}"`.
