---
type: endpoint
tags: []
updated: 2026-04-25
---

# POST /todos

**Authentication:** None

**Purpose:** Create a todo from `{title, owner_id, due_at?}`. `owner_id` is taken from the request body, not validated against existing users.
