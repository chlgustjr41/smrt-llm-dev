"""
todo-api — intentionally buggy FastAPI app for SMRT Agent evaluation.

Five logical bugs are planted here for the QA-Coder loop to discover.
See BUGS.md (hidden from agents via .gitignore) for the answer key.
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

app = FastAPI(title="Todo API", version="1.0.0")

# ─── In-memory state ────────────────────────────────────────────────────────

_users: dict[int, dict] = {}
_todos: dict[int, dict] = {}
_user_seq = 0
_todo_seq = 0
_completed_count = 0  # BUG #5: unprotected shared counter


# ─── Schemas ────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str


class TodoCreate(BaseModel):
    title: str
    owner_id: int
    due_at: Optional[datetime] = None


class TodoPatch(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _save_todo(todo: dict) -> None:
    """Persist a todo to in-memory store (simulates async DB write)."""
    await asyncio.sleep(0)  # yield to event loop
    _todos[todo["id"]] = todo


# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ─── Users ───────────────────────────────────────────────────────────────────

@app.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate):
    global _user_seq
    _user_seq += 1
    user = {
        "id": _user_seq,
        "email": body.email,
        "password_hash": f"hashed:{body.password}",  # never expose in responses
    }
    _users[_user_seq] = user
    return user  # BUG #1: password_hash exposed in response


@app.get("/users")
async def list_users():
    return list(_users.values())  # BUG #1: password_hash exposed for all users


# ─── Todos ───────────────────────────────────────────────────────────────────

@app.post("/todos", status_code=status.HTTP_201_CREATED)
async def create_todo(body: TodoCreate):
    global _todo_seq
    _todo_seq += 1

    # BUG #4: due_at is accepted even if it is in the past
    todo = {
        "id": _todo_seq,
        "title": body.title,
        "owner_id": body.owner_id,
        "due_at": body.due_at.isoformat() if body.due_at else None,
        "done": False,
    }

    _save_todo(todo)  # BUG #2: missing `await` — write is silently dropped
    return todo


@app.get("/todos")
async def list_todos():
    return list(_todos.values())


@app.patch("/todos/{todo_id}")
async def patch_todo(todo_id: int, body: TodoPatch, caller_id: int = 0):
    todo = _todos.get(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    if body.title is not None:
        todo["title"] = body.title
    if body.done is not None:
        todo["done"] = body.done
    return todo


@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: int, caller_id: int = 0):
    todo = _todos.get(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")

    # BUG #3: ownership check happens AFTER the delete
    del _todos[todo_id]

    if todo["owner_id"] != caller_id:
        raise HTTPException(status_code=403, detail="Not your todo")


# ─── Stats ───────────────────────────────────────────────────────────────────

@app.patch("/todos/{todo_id}/complete")
async def complete_todo(todo_id: int):
    global _completed_count
    todo = _todos.get(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    todo["done"] = True

    # BUG #5: read-then-write without a lock; lost updates under concurrency
    current = _completed_count
    await asyncio.sleep(0)       # yield — another request can slip in here
    _completed_count = current + 1

    return {"todo_id": todo_id, "completed_count": _completed_count}


@app.get("/stats")
async def get_stats():
    return {"completed_count": _completed_count, "total": len(_todos)}
