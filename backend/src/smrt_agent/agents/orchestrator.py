"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest, collect_coverage
from smrt_agent.agents.qa.budget import compute_cost_usd as _qa_cost
from smrt_agent.fix_summary import (
    FILE_WRITE_TOOLS,
    _extract_file_path,
    load_events_from_jsonl,
)
from smrt_agent.llm import LLMClient, NormalizedTextBlock


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_pending_pr(project_path: Path, ticket_id: str, session_id: str, recheck_output: str) -> None:
    """Append a pending PR entry to .smrt/pending-prs.jsonl."""
    pr_log = project_path / ".smrt" / "pending-prs.jsonl"
    pr_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ticket_id": ticket_id,
        "session_id": session_id,
        "recheck_output": recheck_output[:500],
        "fixed_at": _ts(),
    }
    with pr_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _analyze_fix_failure(recheck_outputs: list[str]) -> dict[str, str]:
    """Heuristic: guess if ticket needs more attempts or isn't a real bug."""
    import re

    def count_failures(output: str) -> int:
        m = re.search(r"(\d+) failed", output)
        return int(m.group(1)) if m else 0

    if not recheck_outputs:
        return {
            "recommendation": "needs_more_attempts",
            "analysis": (
                "No recheck data was collected. The coder may not have produced any changes. "
                "Consider reviewing the ticket description or increasing the budget."
            ),
        }

    first_failures = count_failures(recheck_outputs[0])
    last_failures = count_failures(recheck_outputs[-1])
    all_same = all(count_failures(o) == first_failures for o in recheck_outputs)

    if all_same and first_failures == 0:
        return {
            "recommendation": "possibly_not_a_bug",
            "analysis": (
                f"All {len(recheck_outputs)} fix attempts completed with 0 test failures throughout. "
                "The existing test suite may not cover this issue, or the ticket may be a "
                "documentation gap, enhancement request, or false positive rather than an actual bug. "
                "Consider closing this ticket or adding a targeted test before re-queueing."
            ),
        }
    if all_same:
        return {
            "recommendation": "possibly_not_a_bug",
            "analysis": (
                f"All {len(recheck_outputs)} attempts produced the same failure count "
                f"({first_failures} failures) — the coder made no measurable progress. "
                "This often means: (1) the bug is in a location the coder cannot pinpoint from the "
                "ticket description alone, (2) the ticket description is ambiguous or incorrect, or "
                "(3) the fix requires architectural changes beyond what a single-pass coder can safely make."
            ),
        }
    if last_failures < first_failures:
        return {
            "recommendation": "needs_more_attempts",
            "analysis": (
                f"Failures decreased from {first_failures} → {last_failures} over "
                f"{len(recheck_outputs)} attempts — the coder is making progress. "
                "Increasing max_fix_attempts in Config or triggering a new fix session "
                "from the current state is likely to succeed."
            ),
        }
    return {
        "recommendation": "needs_more_attempts",
        "analysis": (
            f"After {len(recheck_outputs)} attempts tests still show {last_failures} failures. "
            "The coder's approach may need revision. Try reviewing the coder's changes manually, "
            "refining the ticket description, or increasing max_fix_attempts."
        ),
    }


def _faulty_test_analysis(qa_advice: str, attempt: int) -> dict[str, str]:
    """Build the failure-report payload when QA Advisor declares the test itself
    is buggy. The QA's own analysis (qa_advice) is the substantive payload —
    typically a description of which test file is wrong and how to update it."""
    body = qa_advice.strip() or (
        "QA Advisor flagged the generated test file as faulty but did not "
        "provide a specific update. Manually review .smrt/tests/ for the "
        "test exercising this ticket."
    )
    return {
        "recommendation": "test_faulty",
        "analysis": (
            f"After attempt {attempt + 1}, the QA Advisor concluded that the "
            f"generated test itself is buggy — not the source code under test. "
            f"The fix loop was halted to avoid wasting attempts on a test that "
            f"would never pass.\n\n"
            f"QA Advisor explanation and proposed test-file update:\n\n{body}"
        ),
    }


def _record_failed_fix(
    project_path: Path, ticket_id: str, session_id: str, analysis: dict[str, str]
) -> None:
    """Append a loop-exhausted entry to .smrt/failed-fixes.jsonl."""
    log_path = project_path / ".smrt" / "failed-fixes.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ticket_id": ticket_id,
            "session_id": session_id,
            "recommendation": analysis["recommendation"],
            "analysis": analysis["analysis"],
            "ts": _ts(),
        }) + "\n")


_QA_SATISFIED_SIGNAL = "[QA_SATISFIED]"
_QA_TEST_FAULTY_SIGNAL = "[QA_TEST_FAULTY]"


async def _get_qa_feedback(
    *,
    ticket_content: str,
    recheck_output: str,
    attempt: int,
    max_fix_attempts: int,
    llm_client: LLMClient,
    model: str,
    queue: asyncio.Queue,
    ticket_id: str = "",
    session_id: str = "",
) -> tuple[str, bool, bool]:
    """Ask QA agent to analyze a failed fix and produce guidance for the next attempt.

    Returns (feedback_text, satisfied, test_faulty):
      - satisfied=True  → CASE A: QA declared the fix complete despite failing
                         tests (unrelated failures). Loop ends as success (PR ready).
      - test_faulty=True → CASE C: QA declared the generated test itself buggy.
                         Loop ends as failure routed to Needs Review with a
                         test-update request.
      - both False      → CASE B: actionable feedback for the next attempt.

    Emits session_status "qa_advising", streams qa_text_delta events, and
    emits qa_feedback_done.
    """
    await queue.put({
        "type": "session_status",
        "status": "qa_advising",
        "fix_attempt": attempt,
        "ts": _ts(),
    })

    attempts_left = max(0, max_fix_attempts - attempt - 1)
    is_last = attempts_left == 0
    budget_note = (
        f"Loop budget: this was attempt {attempt + 1} of {max_fix_attempts}"
        f" — {attempts_left} attempt(s) remain. "
        + (
            "After this verdict the loop ENDS (no more retries), so be decisive."
            if is_last
            else "Your CASE B feedback should be precise enough that the next "
            "attempt does not repeat the same approach."
        )
    )

    system = (
        "You are the senior QA engineer who wrote the bug ticket below. "
        "The coder has made a fix attempt. Analyze the pytest output carefully.\n\n"
        f"{budget_note}\n\n"
        "CASE A — the fix IS correct: all failures are unrelated to the bug (e.g. pre-existing "
        "flaky tests, environmental issues, or tests for other features). "
        "In that case, explain why the fix is correct and end your response with the exact token: "
        f"{_QA_SATISFIED_SIGNAL}\n\n"
        "CASE B — the fix is NOT correct AND the bug is real: provide specific, actionable "
        "guidance for the next attempt (3-5 sentences). Identify exactly what was wrong with the "
        "previous approach so the next attempt does not repeat it. Focus on the root cause and "
        "what to try differently. Do NOT include either signal token.\n\n"
        "CASE C — the GENERATED TEST itself is buggy (not the source code): the test has wrong "
        "assertions, the wrong endpoint URL, the wrong fixture setup, an incorrect status code "
        "expectation, or otherwise asserts behavior the spec does not require. In that case the "
        "coder will never make this test pass even with a perfect fix. Explain which test file "
        "needs updating and exactly what the corrected test should look like (1-3 paragraphs, "
        "with a code-block snippet of the corrected test if helpful), then end your response "
        "with the exact token: "
        f"{_QA_TEST_FAULTY_SIGNAL}\n\n"
        "Choose CASE C only when you are confident the test is the problem, not the source — "
        "this halts the loop and routes the ticket to human review."
    )
    user_msg = (
        f"Original bug ticket:\n{ticket_content}\n\n"
        f"Fix attempt {attempt + 1} pytest output:\n```\n{recheck_output}\n```\n\n"
        "Is the fix correct (CASE A), is the source still wrong (CASE B), "
        "or is the generated test itself faulty (CASE C)? Respond accordingly."
    )
    messages: list[dict] = [{"role": "user", "content": user_msg}]
    collected: list[str] = []

    async def on_text(text: str) -> None:
        collected.append(text)
        await queue.put({"type": "qa_text_delta", "text": text, "agent": "qa", "ts": _ts()})

    response = await llm_client.stream_turn(
        system=system,
        tools=[],
        messages=messages,
        model=model,
        on_text=on_text,
    )

    raw = "".join(collected).strip()
    # CASE C wins over CASE A if (somehow) both tokens were emitted — declaring
    # the test faulty is the more conservative outcome (routes to human review
    # instead of marking ready-to-merge).
    test_faulty = _QA_TEST_FAULTY_SIGNAL in raw
    satisfied = (not test_faulty) and (_QA_SATISFIED_SIGNAL in raw)
    feedback = raw.replace(_QA_SATISFIED_SIGNAL, "").replace(_QA_TEST_FAULTY_SIGNAL, "").strip()

    feedback_cost = _qa_cost(response.input_tokens, response.output_tokens, model)
    await queue.put({
        "type": "qa_feedback_done",
        "model": model,
        "total_input_tokens": response.input_tokens,
        "total_output_tokens": response.output_tokens,
        "cost_usd": round(feedback_cost, 6),
        "ts": _ts(),
    })

    if satisfied:
        await queue.put({
            "type": "qa_early_exit",
            "ticket_id": ticket_id,
            "session_id": session_id,
            "reasoning": feedback,
            "ts": _ts(),
        })

    return feedback, satisfied, test_faulty


def _collect_existing_docs(project_path: Path) -> dict:
    """Snapshot the project's existing documentation so the Reviewer can
    decide whether the fix invalidates anything documented.

    Returns:
        project_md: full text of .smrt/Project.md (or "" if missing)
        readme: README.md content, capped to head + tail when very long
        docs_index: list of dicts {path, head} for every docs/*.md file —
            full content of small files, just the first lines of large ones,
            so the Reviewer has enough signal to identify which docs touch
            the same area as the fix without us blowing the context window.

    Cap rules:
        - README.md: up to ~3000 chars head + last 500 chars tail
        - docs/*.md: full content if <= 1500 chars, else first 800 chars
        - Total docs/* output capped at ~12 KB; remaining files are listed
          by path only with a "(content omitted)" marker
    """
    out: dict = {"project_md": "", "readme": "", "docs_index": []}

    pmd = project_path / ".smrt" / "Project.md"
    if pmd.exists():
        try:
            out["project_md"] = pmd.read_text(encoding="utf-8", errors="replace")
        except OSError:
            out["project_md"] = ""

    readme = project_path / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
            if len(text) <= 3500:
                out["readme"] = text
            else:
                out["readme"] = (
                    text[:3000]
                    + "\n\n... (middle truncated) ...\n\n"
                    + text[-500:]
                )
        except OSError:
            out["readme"] = ""

    docs_root = project_path / "docs"
    if docs_root.exists():
        budget = 12_000  # rough char budget across all docs/* entries combined
        used = 0
        for md_file in sorted(docs_root.rglob("*.md")):
            rel = str(md_file.relative_to(project_path)).replace("\\", "/")
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if used >= budget:
                # Beyond the budget — surface the file path only so the
                # Reviewer at least knows it exists and can name it in a
                # proposed update without seeing its content.
                out["docs_index"].append({"path": rel, "head": "(content omitted — beyond context budget)"})
                continue
            head = text if len(text) <= 1500 else (text[:800] + "\n... (truncated) ...")
            used += len(head)
            out["docs_index"].append({"path": rel, "head": head})

    return out


def _summarize_coder_evidence(project_path: Path, session_id: str) -> dict:
    """Read this session's JSONL log and extract evidence of what the Coder
    actually did. The QA Final Summary uses this to ground its narrative in
    fact instead of hallucinating fixes that never happened.

    Returns:
        files_edited: unique file paths the Coder wrote to (across ALL
            attempts, in first-write order).
        total_edits: total count of file-write tool calls. ZERO is a
            meaningful value: it means the Coder examined the code and
            chose NOT to make any change — the Final Summary must reflect
            that distinct outcome rather than confabulate a fix.
        coder_final_reasoning: trailing portion of the most recent Coder
            phase's text-delta stream. This is "what the Coder said before
            stopping" — typically the explicit verdict ("the bug is already
            fixed", "I see no issue here", or a description of the change).

    Best-effort: returns an empty/zero record if the JSONL can't be read.
    """
    try:
        events = load_events_from_jsonl(project_path, session_id)
    except Exception:
        return {"files_edited": [], "total_edits": 0, "coder_final_reasoning": ""}

    files_edited: list[str] = []
    total_edits = 0
    last_coder_text = ""
    pending_coder_text = ""

    for ev in events:
        t = ev.get("type")
        if t == "session_status" and ev.get("status") == "coder_running":
            # New Coder phase starts: discard any prior pending text so we
            # only retain narration from the MOST RECENT Coder attempt.
            # Earlier-attempt narration is interesting but stale, and would
            # confuse the QA's "what was the final verdict" reasoning.
            pending_coder_text = ""
        elif t == "session_status":
            # Any other phase boundary closes the running text capture.
            if pending_coder_text:
                last_coder_text = pending_coder_text
                pending_coder_text = ""
        elif t == "coder_text_delta":
            pending_coder_text += ev.get("text", "") or ""
        elif t == "tool_use" and ev.get("tool") in FILE_WRITE_TOOLS:
            path = _extract_file_path(ev.get("input"))
            if isinstance(path, str):
                if path not in files_edited:
                    files_edited.append(path)
                total_edits += 1

    if pending_coder_text:
        last_coder_text = pending_coder_text

    # Cap the reasoning so the QA prompt doesn't balloon — the tail is the
    # most relevant part (the Coder's final statement before yielding back).
    return {
        "files_edited": files_edited,
        "total_edits": total_edits,
        "coder_final_reasoning": last_coder_text.strip()[-1500:],
    }


_DOC_UPDATES_OPEN = "[DOC_UPDATES_JSON]"
_DOC_UPDATES_CLOSE = "[/DOC_UPDATES_JSON]"


def _parse_doc_updates(raw: str) -> list[dict]:
    """Pull the structured proposed_doc_updates list from the Reviewer's
    streamed text. Tolerates missing or malformed JSON (returns []) so the
    narrative is never lost just because the JSON tail is bad.

    Recognized shape:
        [DOC_UPDATES_JSON]
        {"updates": [
            {"path": "docs/architecture.md",
             "reason": "describe why",
             "new_content": "full file content"}
        ]}
        [/DOC_UPDATES_JSON]
    """
    start = raw.find(_DOC_UPDATES_OPEN)
    if start < 0:
        return []
    end = raw.find(_DOC_UPDATES_CLOSE, start)
    if end < 0:
        return []
    payload = raw[start + len(_DOC_UPDATES_OPEN):end].strip()
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return []
    raw_updates = obj.get("updates") if isinstance(obj, dict) else None
    if not isinstance(raw_updates, list):
        return []
    cleaned: list[dict] = []
    for u in raw_updates:
        if not isinstance(u, dict):
            continue
        path = u.get("path")
        new_content = u.get("new_content")
        # Only accept proposals with the minimum viable fields. The reason
        # field is allowed to be empty since the Reviewer may inline it
        # in the narrative; we just want path + content to be applicable.
        if isinstance(path, str) and isinstance(new_content, str) and path.strip():
            cleaned.append({
                "path": path.strip(),
                "reason": str(u.get("reason", "")).strip(),
                "new_content": new_content,
            })
    return cleaned


def _strip_doc_updates_block(raw: str) -> str:
    """Return the narrative portion only — strips the JSON tail used for
    machine-applicable proposals so the user-facing summary stays clean."""
    start = raw.find(_DOC_UPDATES_OPEN)
    if start < 0:
        return raw.strip()
    return raw[:start].rstrip()


async def _get_reviewer_final_summary(
    *,
    ticket_content: str,
    recheck_outputs: list[str],
    final_status: str,
    final_recommendation: str | None,
    extra_context: str | None,
    llm_client: LLMClient,
    model: str,
    queue: asyncio.Queue,
    project_path: Path,
    ticket_id: str = "",
    session_id: str = "",
) -> str:
    """Stream a Reviewer-written narrative wrap-up at the very end of the
    fix loop, plus structured proposed_doc_updates for files in the project's
    documentation tree.

    The Reviewer is the *third agent* — distinct from the Coder (who wrote
    the fix) and the QA agent (who verified it). The Reviewer holds the
    documentation context (Project.md, README, docs/*) and is best
    positioned to (a) write an objective summary of the fix and (b) flag
    when the fix invalidates something documented elsewhere.

    Always run before the final session_status emission, regardless of
    outcome (done, loop_exhausted, test_faulty, error). The proposed doc
    updates are applied when the user accepts the ticket from Needs Review.

    Emits:
      - session_status: reviewer_summarizing  → creates the timeline phase
        that appears AFTER the last Coder/QA Verify so reviewers always see
        a Reviewer wrap-up at the bottom of the timeline.
      - reviewer_text_delta (streamed)        → live token stream for the UI.
      - qa_feedback_done                      → cost accounting (reused for
        consistency with other terminal LLM calls).
      - reviewer_final_summary                → durable record with the full
        narrative AND the parsed proposed_doc_updates list. This event is
        what `build_fix_summary_from_events` picks up to populate the
        persisted Fix Summary's headline narrative + doc-update queue.

    Returns the narrative summary string (best-effort: empty string on
    LLM failure so callers never block the loop's terminal status event).
    """
    await queue.put({
        "type": "session_status",
        "status": "reviewer_summarizing",
        "ts": _ts(),
    })

    # Read the agent log on a worker thread so we don't block the event loop
    # while the JSONL is parsed. By this point all prior events for the
    # session have been persisted (EventLogger.put awaits each disk write),
    # so the log is the ground truth of what the Coder did.
    coder_evidence = await asyncio.to_thread(
        _summarize_coder_evidence, project_path, session_id
    )
    # Snapshot the existing project docs so the Reviewer can decide which
    # ones the fix invalidates and propose targeted updates.
    existing_docs = await asyncio.to_thread(_collect_existing_docs, project_path)

    last_recheck = recheck_outputs[-1] if recheck_outputs else "(no pytest output captured)"
    attempt_count = len(recheck_outputs)
    attempt_word = "attempt" if attempt_count == 1 else "attempts"
    no_changes_made = coder_evidence["total_edits"] == 0

    outcome_clause = {
        "done": (
            "The loop ENDED IN SUCCESS — the final pytest run is green and the "
            "fix is being prepared for review."
        ),
        "loop_exhausted": (
            "The loop ENDED WITHOUT A WORKING FIX — the ticket is being routed "
            "to human review."
        ),
    }.get(final_status, f"The loop ended with status: {final_status}.")

    rec_clause = ""
    if final_recommendation == "test_faulty":
        rec_clause = (
            "Note: a previous QA verdict in this loop classified the generated "
            "test itself as faulty. Make sure your summary explains the test "
            "issue and the proposed test-file update."
        )
    elif final_recommendation == "needs_more_attempts":
        rec_clause = (
            "Note: the loop heuristic recommends giving the coder more attempts. "
            "Reflect this in your summary if you agree, or explain why a "
            "different approach is needed."
        )
    elif final_recommendation == "possibly_not_a_bug":
        rec_clause = (
            "Note: the loop heuristic suggests this may not be a real bug. "
            "If you agree, say so explicitly so the reviewer can close the "
            "ticket without further work."
        )

    extra_clause = (
        f"\n\nAdditional context from the loop:\n{extra_context}" if extra_context else ""
    )

    # Evidence block: ground the model in what actually happened. Without
    # this, the model defaults to its training-data prior of "tests pass →
    # there must have been a fix" and confabulates changes that never
    # occurred. The coder_final_reasoning is especially valuable when
    # total_edits == 0 — it captures the Coder's explicit verdict.
    files_listing = ", ".join(coder_evidence["files_edited"]) or "(none)"
    coder_text = coder_evidence["coder_final_reasoning"] or "(no Coder narration captured)"
    evidence_block = (
        "\n\n──────── VERIFIED EVIDENCE FROM AGENT LOG ────────\n"
        f"Total file edits the Coder made: {coder_evidence['total_edits']}\n"
        f"Files edited (unique): {files_listing}\n"
        "Coder's reasoning text from the most recent attempt:\n"
        f"```\n{coder_text}\n```\n"
        "──────────────────────────────────────────────────\n"
    )

    # The no-op clause is the structural fix for the user-reported bug:
    # when the Coder makes ZERO edits, that is itself a meaningful outcome,
    # not a missing piece of information. Refusing to invent fixes here is
    # a hard requirement — the prompt forces the model to say "no source
    # files were modified" and to surface the Coder's reasoning verbatim.
    no_op_clause = ""
    if no_changes_made:
        no_op_clause = (
            "\n\n**CRITICAL — NO SOURCE FILES WERE MODIFIED IN THIS LOOP.**\n"
            "The Coder examined the source and chose NOT to make any edit. "
            "This is a deliberate decision, not a bug in the loop. Common reasons:\n"
            "  - The bug was already fixed in a previous session or by manual edit.\n"
            "  - The reported behavior turns out to match the spec (false positive).\n"
            "  - The fix needed is outside the Coder's scope (test file, config, deps).\n\n"
            "Your '## What changed' section MUST literally start with "
            "`No source files were modified during this fix loop.` followed by a "
            "single sentence quoting the Coder's verdict.\n"
            "Your '## Why this works (or what went wrong)' section MUST explain the "
            "Coder's reasoning, citing the verified evidence above. DO NOT invent "
            "file edits, line numbers, or function changes — there were none."
        )

    # Build the docs context block. We surface Project.md (full), README.md
    # (head + tail), and an index of docs/* files (full content for small
    # ones, heads for large ones). Without this the Reviewer would propose
    # generic updates like "add a note about the fix" without specific
    # content to apply.
    project_md_block = (
        f"### .smrt/Project.md\n```markdown\n{existing_docs['project_md']}\n```\n"
        if existing_docs["project_md"]
        else "### .smrt/Project.md\n_(file does not exist)_\n"
    )
    readme_block = (
        f"### README.md (head + tail; full content in repo)\n```markdown\n{existing_docs['readme']}\n```\n"
        if existing_docs["readme"]
        else "### README.md\n_(file does not exist)_\n"
    )
    if existing_docs["docs_index"]:
        docs_lines = ["### docs/* index"]
        for d in existing_docs["docs_index"]:
            docs_lines.append(f"#### `{d['path']}`\n```markdown\n{d['head']}\n```")
        docs_block = "\n".join(docs_lines)
    else:
        docs_block = "### docs/*\n_(no documentation files yet)_"

    docs_context_block = (
        "\n\n──────── EXISTING DOCUMENTATION SNAPSHOT ────────\n"
        "These are the project's existing docs. After your narrative, propose "
        "any updates to these files that the fix necessitates (e.g., a "
        "documented invariant changed, a new behavior needs noting, an "
        "architectural decision was reversed). If nothing needs updating, "
        "emit an empty updates list.\n\n"
        f"{project_md_block}\n{readme_block}\n{docs_block}\n"
        "─────────────────────────────────────────────────\n"
    )

    system = (
        "You are the **Reviewer agent** — the third perspective on this "
        "QA→Coder fix loop. The Coder wrote the fix, the QA agent verified "
        "it, and you (Reviewer) hold the documentation context. Your job "
        "is to write the COMPILED FIX SUMMARY (the durable record reviewers "
        "see when they open the ticket) AND propose any documentation "
        "updates the fix necessitates.\n\n"
        f"{outcome_clause}\n\n"
        f"{rec_clause}"
        f"{evidence_block}"
        f"{no_op_clause}"
        f"{docs_context_block}\n\n"
        "## Output format\n\n"
        "First, write the FIX SUMMARY as concise GitHub-flavored markdown "
        "with these sections:\n"
        "  ## What the bug was\n"
        "    One-paragraph plain-English description of the original problem.\n"
        "  ## What changed\n"
        "    A bulleted list of the substantive changes the Coder made — and ONLY\n"
        "    files that appear in the verified evidence above. Reference exact file\n"
        "    paths from the evidence; do NOT name files that were not edited.\n"
        "    If the evidence shows zero edits, follow the no-op instructions above.\n"
        "  ## Why this works (or what went wrong)\n"
        "    For successful fixes WITH edits: explain the root cause and how the\n"
        "    edited files address it.\n"
        "    For successful runs with NO edits: explain (citing the Coder's verdict)\n"
        "    why the bug appears already fixed or not actionable.\n"
        "    For failed loops: explain what the Coder tried (or why they didn't try),\n"
        "    why it didn't work, and what a human reviewer should investigate next.\n"
        "  ## Final test status\n"
        "    One or two lines summarizing the final pytest output.\n"
        "  ## Documentation impact\n"
        "    Brief prose: which docs files (if any) should be updated and why.\n"
        "    If none, say 'No documentation updates required.'\n\n"
        "Then, AFTER the markdown, emit a structured proposed-updates block "
        "the system can apply machine-readably. The block MUST be exactly:\n\n"
        f"{_DOC_UPDATES_OPEN}\n"
        "{\"updates\": [\n"
        "  {\"path\": \"docs/architecture.md\",\n"
        "   \"reason\": \"why this update is needed\",\n"
        "   \"new_content\": \"FULL replacement content for the file\"}\n"
        "]}\n"
        f"{_DOC_UPDATES_CLOSE}\n\n"
        "Rules for the updates block:\n"
        "  - `path` MUST be one of: 'README.md', '.smrt/Project.md', or "
        "    'docs/<...>.md'. No other paths are accepted.\n"
        "  - `new_content` is the COMPLETE new file contents (not a diff). "
        "    The system writes the file verbatim from this string.\n"
        "  - Only propose updates that are actually warranted by the fix. "
        "    If nothing needs updating, emit `{\"updates\": []}`.\n"
        "  - Be conservative: the user must approve before these are written. "
        "    Don't propose stylistic rewrites — only updates whose absence "
        "    would leave the docs out of sync with the fixed behavior.\n\n"
        "Be factual. The verified evidence is the ground truth — your "
        "summary must be consistent with it. Keep the markdown narrative "
        "under ~400 words."
    )
    user_msg = (
        f"Bug ticket (with any in-loop QA feedback already appended):\n"
        f"```\n{ticket_content}\n```\n\n"
        f"Loop ran for {attempt_count} {attempt_word}. "
        f"Final pytest output:\n```\n{last_recheck}\n```"
        f"{extra_clause}\n\n"
        "Write the compiled Fix Summary now (markdown narrative, then the "
        "[DOC_UPDATES_JSON] block), grounded in the verified evidence and "
        "documentation snapshot from the system message."
    )
    messages: list[dict] = [{"role": "user", "content": user_msg}]
    collected: list[str] = []

    async def on_text(text: str) -> None:
        collected.append(text)
        # text_delta with agent='reviewer' so the AgentTimeline routes the
        # streamed tokens to the new "Reviewer Summary" phase (blue brand).
        await queue.put({
            "type": "reviewer_text_delta",
            "text": text,
            "agent": "reviewer",
            "ts": _ts(),
        })

    try:
        response = await llm_client.stream_turn(
            system=system,
            tools=[],
            messages=messages,
            model=model,
            on_text=on_text,
        )
    except Exception as exc:
        # Best-effort: the Reviewer narrative is valuable but not critical.
        # If the LLM call fails, still emit a final_summary event so the
        # UI doesn't hang and the persisted summary records the failure.
        await queue.put({
            "type": "reviewer_final_summary",
            "ticket_id": ticket_id,
            "session_id": session_id,
            "summary": "",
            "proposed_doc_updates": [],
            "error": f"Reviewer final summary failed: {exc}",
            "ts": _ts(),
        })
        return ""

    raw = "".join(collected).strip()
    # Split the raw response into the user-facing narrative and the
    # machine-applicable JSON block. Both go onto the persisted summary so
    # the UI can render the narrative and the Accept handler can apply the
    # proposed updates.
    summary = _strip_doc_updates_block(raw)
    proposed_updates = _parse_doc_updates(raw)

    feedback_cost = _qa_cost(response.input_tokens, response.output_tokens, model)
    await queue.put({
        "type": "qa_feedback_done",
        "model": model,
        "total_input_tokens": response.input_tokens,
        "total_output_tokens": response.output_tokens,
        "cost_usd": round(feedback_cost, 6),
        "ts": _ts(),
    })
    await queue.put({
        "type": "reviewer_final_summary",
        "ticket_id": ticket_id,
        "session_id": session_id,
        "summary": summary,
        "proposed_doc_updates": proposed_updates,
        "final_status": final_status,
        "ts": _ts(),
    })
    return summary


async def run_qa_session(
    *,
    session_id: str,
    project_path: Path,
    llm_client: LLMClient,
    model_qa: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int = 0,
    max_questions_per_attempt: int = 0,
    queue: asyncio.Queue,
    job_id: str | None = None,
) -> str:
    """Run one QA discovery pass. Files tickets into pending_confirmation; coder loop is
    triggered separately when the user approves a ticket via the kanban board."""
    await queue.put({
        "type": "session_status",
        "status": "qa_running",
        "fix_attempt": 0,
        "ts": _ts(),
    })

    ticket_id = await run_qa_agent(
        project_path=project_path,
        llm_client=llm_client,
        model=model_qa,
        budget_usd=budget_usd,
        queue=queue,
        job_id=job_id,
    )

    if ticket_id is None:
        await queue.put({
            "type": "session_status",
            "status": "done",
            "fix_attempt": 0,
            "ts": _ts(),
        })
        return "done"

    # Ticket filed — emit hitl_request so the frontend can count tickets filed,
    # then immediately end the session. The ticket stays in pending_confirmation
    # until the user approves it via the kanban board.
    await queue.put({
        "type": "hitl_request",
        "session_id": session_id,
        "ticket_id": ticket_id,
        "fix_attempt": 0,
        "ts": _ts(),
    })
    await queue.put({
        "type": "session_status",
        "status": "done",
        "fix_attempt": 0,
        "ts": _ts(),
    })
    return "done"


async def run_ticket_fix_session(
    *,
    session_id: str,
    ticket_id: str,
    project_path: Path,
    llm_client: LLMClient,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
    queue: asyncio.Queue,
    on_status_change: Callable[[str], Awaitable[None]] | None = None,
    model_qa: str | None = None,
    model_reviewer: str | None = None,
    max_questions_per_attempt: int = 0,
    job_id: str | None = None,
) -> str:
    """Run Coder → pytest-verify loop for a specific approved ticket.

    Status transitions emitted to queue and via on_status_change callback:
      coder_running  → Coder agent is editing source files
      qa_checking    → Pytest recheck is running (QA verify)
      done           → Tests green; PR entry recorded in pending-prs.jsonl
      error          → Max attempts exhausted
    """
    ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
    ticket_content = (
        ticket_path.read_text(encoding="utf-8")
        if ticket_path.exists()
        else f"Ticket {ticket_id}: content not found"
    )

    recheck_outputs: list[str] = []

    for attempt in range(max_fix_attempts):
        # ── Coder phase ──────────────────────────────────────────────────────
        if on_status_change:
            await on_status_change("coder_running")
        await queue.put({
            "type": "session_status",
            "status": "coder_running",
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        # Pytest must run in a thread — synchronous subprocess.run blocks the
        # asyncio loop for the whole timeout period, freezing SSE/JSONL writes
        # and making the UI appear stuck on "Awaiting activity…" until pytest
        # either completes or times out (potentially 60–120s).
        await queue.put({"type": "pytest_running", "phase": "pre_coder", "ts": _ts()})
        pytest_output = await asyncio.to_thread(run_pytest, project_path)
        await queue.put({
            "type": "pytest_done",
            "phase": "pre_coder",
            "summary": pytest_output[:500],
            "ts": _ts(),
        })

        await run_coder_agent(
            project_path=project_path,
            llm_client=llm_client,
            model=model_coder,
            budget_usd=budget_usd,
            queue=queue,
            ticket_content=ticket_content,
            pytest_output=pytest_output,
            llm_client_qa=llm_client if model_qa else None,
            model_qa=model_qa,
            max_questions=max_questions_per_attempt,
            job_id=job_id,
            attempt_index=attempt,
            max_fix_attempts=max_fix_attempts,
        )

        # ── QA verification phase ─────────────────────────────────────────
        if on_status_change:
            await on_status_change("qa_checking")
        await queue.put({
            "type": "session_status",
            "status": "qa_checking",
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        await queue.put({"type": "pytest_running", "phase": "qa_verify", "ts": _ts()})
        recheck_output = await asyncio.to_thread(run_pytest, project_path)
        recheck_outputs.append(recheck_output)
        await queue.put({
            "type": "recheck_output",
            "output": recheck_output[:2000],
            "ts": _ts(),
        })

        if "passed" in recheck_output and "failed" not in recheck_output:
            _record_pending_pr(project_path, ticket_id, session_id, recheck_output)
            await asyncio.to_thread(collect_coverage, project_path)
            await queue.put({
                "type": "pr_ready",
                "ticket_id": ticket_id,
                "session_id": session_id,
                "ts": _ts(),
            })
            # Final QA narrative — runs even on first-pass success so every
            # successful ticket has a "QA Final Summary" phase visible after
            # the Coder/QA Verify sections, plus a durable narrative in the
            # persisted Fix Summary.
            if model_qa:
                await _get_reviewer_final_summary(
                    ticket_content=ticket_content,
                    recheck_outputs=recheck_outputs,
                    final_status="done",
                    final_recommendation=None,
                    extra_context=None,
                    llm_client=llm_client,
                    # Fall back to model_qa when no dedicated reviewer model
                    # is configured, so older project configs keep working.
                    model=model_reviewer or model_qa,
                    queue=queue,
                    project_path=project_path,
                    ticket_id=ticket_id,
                    session_id=session_id,
                )
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        await queue.put({
            "type": "fix_attempt_failed",
            "attempt": attempt + 1,
            "max_attempts": max_fix_attempts,
            "recheck": recheck_output[:500],
            "ts": _ts(),
        })

        # Run the QA Advisor on every failed attempt — including the last one.
        # On the last attempt it can still declare CASE C (test_faulty), which
        # routes the ticket to a more useful Needs Review state than the
        # generic loop-exhausted heuristic would produce.
        if model_qa:
            qa_advice, qa_satisfied, qa_test_faulty = await _get_qa_feedback(
                ticket_content=ticket_content,
                recheck_output=recheck_output,
                attempt=attempt,
                max_fix_attempts=max_fix_attempts,
                llm_client=llm_client,
                model=model_qa,
                queue=queue,
                ticket_id=ticket_id,
                session_id=session_id,
            )
            if qa_satisfied:
                # CASE A: QA advisor declared the fix complete despite failing tests
                _record_pending_pr(project_path, ticket_id, session_id, recheck_output)
                await asyncio.to_thread(collect_coverage, project_path)
                await queue.put({"type": "pr_ready", "ticket_id": ticket_id, "session_id": session_id, "ts": _ts()})
                # Final QA narrative — pass the satisfied verdict as extra
                # context so the summary explains *why* the failing tests are
                # unrelated, not just that the fix is complete.
                await _get_reviewer_final_summary(
                    ticket_content=ticket_content,
                    recheck_outputs=recheck_outputs,
                    final_status="done",
                    final_recommendation=None,
                    extra_context=(
                        "The QA Advisor declared CASE A (fix correct, failing "
                        "tests unrelated). Their reasoning was:\n" + qa_advice
                    ),
                    llm_client=llm_client,
                    # Fall back to model_qa when no dedicated reviewer model
                    # is configured, so older project configs keep working.
                    model=model_reviewer or model_qa,
                    queue=queue,
                    project_path=project_path,
                    ticket_id=ticket_id,
                    session_id=session_id,
                )
                await queue.put({"type": "session_status", "status": "done", "fix_attempt": attempt, "ts": _ts()})
                return "done"
            if qa_test_faulty:
                # CASE C: the generated test itself is buggy. Halt the loop and
                # route to Needs Review with a test-update recommendation —
                # further attempts would be wasted on an unwinnable test.
                analysis = _faulty_test_analysis(qa_advice, attempt)
                await asyncio.to_thread(_record_failed_fix, project_path, ticket_id, session_id, analysis)
                await queue.put({
                    "type": "loop_exhausted",
                    "ticket_id": ticket_id,
                    "session_id": session_id,
                    "attempts": attempt + 1,
                    "recommendation": analysis["recommendation"],
                    "analysis": analysis["analysis"],
                    "ts": _ts(),
                })
                # Final QA narrative — surface the test-faulty verdict as
                # extra context so the summary describes the test-update
                # plan in narrative form.
                await _get_reviewer_final_summary(
                    ticket_content=ticket_content,
                    recheck_outputs=recheck_outputs,
                    final_status="loop_exhausted",
                    final_recommendation="test_faulty",
                    extra_context=(
                        "The QA Advisor declared CASE C (test faulty). Their "
                        "test-update analysis was:\n" + qa_advice
                    ),
                    llm_client=llm_client,
                    # Fall back to model_qa when no dedicated reviewer model
                    # is configured, so older project configs keep working.
                    model=model_reviewer or model_qa,
                    queue=queue,
                    project_path=project_path,
                    ticket_id=ticket_id,
                    session_id=session_id,
                )
                await queue.put({
                    "type": "session_status",
                    "status": "loop_exhausted",
                    "message": (
                        "QA Advisor declared the generated test faulty — "
                        "routed to Needs Review with test-update request"
                    ),
                    "ts": _ts(),
                })
                return "loop_exhausted"
            # CASE B: append numbered feedback so the next Coder attempt can
            # learn from the previous failure and avoid repeating the approach.
            if attempt < max_fix_attempts - 1:
                ticket_content = (
                    ticket_content
                    + f"\n\n---\n## QA feedback after attempt {attempt + 1} of {max_fix_attempts}\n\n"
                    + qa_advice
                )

    # All attempts exhausted — generate failure analysis and route to Needs Review
    analysis = _analyze_fix_failure(recheck_outputs)
    await asyncio.to_thread(_record_failed_fix, project_path, ticket_id, session_id, analysis)
    await queue.put({
        "type": "loop_exhausted",
        "ticket_id": ticket_id,
        "session_id": session_id,
        "attempts": max_fix_attempts,
        "recommendation": analysis["recommendation"],
        "analysis": analysis["analysis"],
        "ts": _ts(),
    })
    # Final QA narrative for the exhausted-loop case. The heuristic in
    # _analyze_fix_failure gives a structured recommendation; this pass
    # converts it into a human-readable explanation grounded in the
    # actual ticket text and pytest output.
    if model_reviewer or model_qa:
        await _get_reviewer_final_summary(
            ticket_content=ticket_content,
            recheck_outputs=recheck_outputs,
            final_status="loop_exhausted",
            final_recommendation=analysis["recommendation"],
            extra_context=(
                f"Loop heuristic recommendation: {analysis['recommendation']}\n"
                f"Heuristic analysis: {analysis['analysis']}"
            ),
            llm_client=llm_client,
            model=model_reviewer or model_qa,
            queue=queue,
            project_path=project_path,
            ticket_id=ticket_id,
            session_id=session_id,
        )
    await queue.put({
        "type": "session_status",
        "status": "loop_exhausted",
        "message": f"Max fix attempts ({max_fix_attempts}) reached — routed to Needs Review",
        "ts": _ts(),
    })
    return "loop_exhausted"
