"""FastAPI review interface for AstroTalk content safety workbench"""

from __future__ import annotations

import csv
import io
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Ensure project root is importable when running from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

from store.db import (
    DB_PATH,
    get_connection,
    fetch_sessions,
    fetch_pending_review_sessions,
    update_review_status,
    initialise_db,
)
from store.writer import write_review_action


# ---------------------------------------------------------------------------
# Lifespan — initialise DB (including session_note migration) on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        initialise_db()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AstroTalk Review Workbench",
    description="Content safety review interface — GT Bharat",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_VALID_ACTIONS = {"CONFIRM", "FALSE_POSITIVE", "ESCALATE", "CLEAR"}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str
    reviewer_id: str
    note: str = ""
    flag_id: Optional[int] = None


class ManualFlagRequest(BaseModel):
    turn_id: Optional[int] = None
    category_code: str
    note: str
    reviewer_id: str
    message_text: str


class SessionNoteRequest(BaseModel):
    note: str
    reviewer_id: str


class AmendFlagRequest(BaseModel):
    category_code: str
    severity: str
    reasoning: str
    reviewer_id: str


class DismissFlagRequest(BaseModel):
    reviewer_id: str
    note: str


# ---------------------------------------------------------------------------
# Endpoints — health + aggregate stats
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "db": DB_PATH}


@app.get("/stats")
def stats():
    try:
        with get_connection() as conn:
            total       = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            pending     = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE review_status = 'PENDING'"
            ).fetchone()[0]
            reviewed    = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE review_status != 'PENDING'"
            ).fetchone()[0]
            severe      = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE overall_verdict = 'SEVERE'"
            ).fetchone()[0]
            flagged     = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE overall_verdict = 'FLAGGED'"
            ).fetchone()[0]
            clean       = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE overall_verdict = 'CLEAN'"
            ).fetchone()[0]
            unprocessed = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE overall_verdict = 'UNPROCESSED'"
            ).fetchone()[0]
    except Exception:
        return {
            "total_sessions": 0, "total_pending": 0, "total_reviewed": 0,
            "count_severe": 0, "count_flagged": 0, "count_clean": 0,
            "count_unprocessed": 0,
        }

    return {
        "total_sessions":    total,
        "total_pending":     pending,
        "total_reviewed":    reviewed,
        "count_severe":      severe,
        "count_flagged":     flagged,
        "count_clean":       clean,
        "count_unprocessed": unprocessed,
    }


@app.get("/stats/reviewer")
def reviewer_stats():
    """Per-reviewer activity breakdown — only sessions that have been reviewed."""
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    reviewer_id,
                    COUNT(*) AS sessions_reviewed,
                    SUM(CASE WHEN review_status = 'CONFIRMED'  THEN 1 ELSE 0 END) AS confirmed,
                    SUM(CASE WHEN review_status = 'OVERRIDDEN' THEN 1 ELSE 0 END) AS false_positives,
                    SUM(CASE WHEN review_status = 'ESCALATED'  THEN 1 ELSE 0 END) AS escalated,
                    SUM(CASE WHEN review_status = 'REVIEWED'   THEN 1 ELSE 0 END) AS cleared
                FROM sessions
                WHERE review_status != 'PENDING'
                  AND reviewer_id IS NOT NULL
                GROUP BY reviewer_id
                ORDER BY sessions_reviewed DESC
            """).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


@app.get("/stats/violations")
def violation_stats():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT f.category_code, COUNT(*) AS count
                FROM flags f
                JOIN sessions s ON s.session_id = f.session_id
                WHERE s.overall_verdict != 'CLEAN'
                GROUP BY f.category_code
                ORDER BY count DESC
            """).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Endpoints — session list
# NOTE: /sessions/pending must be defined BEFORE /sessions/{session_id}
# ---------------------------------------------------------------------------

@app.get("/sessions/pending")
def pending_sessions(limit: int = Query(default=50, ge=1, le=500)):
    return fetch_pending_review_sessions(limit=limit)


@app.get("/sessions")
def sessions(
    verdict:  Optional[str] = None,
    status:   Optional[str] = None,
    language: Optional[str] = None,
):
    rows = fetch_sessions(
        verdict_filter=verdict,
        status_filter=status,
        language_filter=language,
    )

    # Enrich each row with flag count (single aggregation query)
    try:
        with get_connection() as conn:
            flag_counts = dict(
                conn.execute(
                    "SELECT session_id, COUNT(*) FROM flags GROUP BY session_id"
                ).fetchall()
            )
        for row in rows:
            row["flag_count"] = flag_counts.get(row["session_id"], 0)
    except Exception:
        for row in rows:
            row["flag_count"] = None

    return rows


# ---------------------------------------------------------------------------
# Endpoints — session detail and sub-resources
# NOTE: more-specific paths (/flags, /review, /manual-flag, /session-note)
# must be defined BEFORE the generic /{session_id} catch-all.
# ---------------------------------------------------------------------------

@app.get("/sessions/{session_id}/flags")
def get_session_flags(session_id: str):
    """
    Returns all flags for a session.
    MANUAL flags are enriched with flagged_by (reviewer_id from review_log).
    """
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT f.*,
                       CASE WHEN f.detection_layer = 'MANUAL'
                            THEN rl.reviewer_id ELSE NULL END AS flagged_by
                FROM flags f
                LEFT JOIN review_log rl
                    ON rl.flag_id = f.flag_id AND rl.action = 'MANUAL_FLAG'
                WHERE f.session_id = ?
                ORDER BY f.flag_id
            """, (session_id,)).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/sessions/{session_id}")
def session_detail(session_id: str):
    """
    Full session detail including turns and flags.
    MANUAL flags include flagged_by from review_log.
    """
    try:
        with get_connection() as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id!r} not found"
                )
            turns = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_id", (session_id,)
            ).fetchall()
            flags = conn.execute("""
                SELECT f.*,
                       CASE WHEN f.detection_layer = 'MANUAL'
                            THEN rl.reviewer_id ELSE NULL END AS flagged_by
                FROM flags f
                LEFT JOIN review_log rl
                    ON rl.flag_id = f.flag_id AND rl.action = 'MANUAL_FLAG'
                WHERE f.session_id = ?
                ORDER BY f.flag_id
            """, (session_id,)).fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "session": dict(session),
        "turns":   [dict(t) for t in turns],
        "flags":   [dict(f) for f in flags],
    }


@app.post("/sessions/{session_id}/review")
def submit_review(session_id: str, body: ReviewRequest):
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action {body.action!r}. Must be one of: {sorted(_VALID_ACTIONS)}",
        )
    try:
        write_review_action(
            session_id, body.flag_id, body.action, body.reviewer_id, body.note
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"success": True, "session_id": session_id}


@app.post("/sessions/{session_id}/manual-flag")
def manual_flag(session_id: str, body: ManualFlagRequest):
    """Insert a reviewer-created flag and record it in the review log."""
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO flags
                    (session_id, turn_id, category_code, detection_layer, severity,
                     confidence_score, reasoning, false_positive_risk, pattern_matched)
                VALUES (?, ?, ?, 'MANUAL', 'MEDIUM', 1.0, ?, 'LOW', ?)
                """,
                (
                    session_id,
                    body.turn_id,
                    body.category_code,
                    body.note,
                    body.message_text[:200],
                ),
            )
            flag_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO review_log (session_id, flag_id, action, reviewer_id, note)
                VALUES (?, ?, 'MANUAL_FLAG', ?, ?)
                """,
                (session_id, flag_id, body.reviewer_id, body.note),
            )
        return {"success": True, "flag_id": flag_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@app.post("/sessions/{session_id}/session-note")
def save_session_note(session_id: str, body: SessionNoteRequest):
    """Persist a reviewer's overall observation note on the session."""
    # Belt-and-suspenders migration in case column is absent in legacy DB
    try:
        with get_connection() as conn:
            conn.execute("ALTER TABLE sessions ADD COLUMN session_note TEXT")
    except Exception:
        pass

    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET session_note = ? WHERE session_id = ?",
                (body.note, session_id),
            )
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints — flag operations
# ---------------------------------------------------------------------------

@app.post("/flags/{flag_id}/amend")
def amend_flag(flag_id: int, body: AmendFlagRequest):
    conn = get_connection()
    try:
        with conn:
            original = conn.execute(
                "SELECT session_id, turn_id FROM flags WHERE flag_id = ?", (flag_id,)
            ).fetchone()
            if original is None:
                raise HTTPException(status_code=404, detail=f"Flag {flag_id} not found")
            cur = conn.execute(
                """
                INSERT INTO flags
                    (session_id, turn_id, category_code, detection_layer, severity,
                     confidence_score, reasoning, false_positive_risk, pattern_matched)
                VALUES (?, ?, ?, 'AMENDED', ?, 1.0, ?, 'LOW', ?)
                """,
                (
                    original["session_id"],
                    original["turn_id"],
                    body.category_code,
                    body.severity,
                    body.reasoning,
                    f"Amended by reviewer: {body.reviewer_id}",
                ),
            )
        return {"success": True, "new_flag_id": cur.lastrowid}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@app.post("/flags/{flag_id}/dismiss")
def dismiss_flag(flag_id: int, body: DismissFlagRequest):
    conn = get_connection()
    try:
        with conn:
            original = conn.execute(
                "SELECT session_id, turn_id, category_code FROM flags WHERE flag_id = ?",
                (flag_id,),
            ).fetchone()
            if original is None:
                raise HTTPException(status_code=404, detail=f"Flag {flag_id} not found")
            conn.execute(
                """
                INSERT INTO flags
                    (session_id, turn_id, category_code, detection_layer, severity,
                     confidence_score, reasoning, false_positive_risk, pattern_matched)
                VALUES (?, ?, ?, 'DISMISSED', 'LOW', 0.0, ?, 'HIGH', ?)
                """,
                (
                    original["session_id"],
                    original["turn_id"],
                    original["category_code"] + "_DISMISSED",
                    f"Dismissed by reviewer: {body.note}",
                    f"Dismissed by reviewer: {body.reviewer_id}",
                ),
            )
            conn.execute(
                """
                INSERT INTO review_log (session_id, flag_id, action, reviewer_id, note)
                VALUES (?, ?, 'FLAG_DISMISSED', ?, ?)
                """,
                (original["session_id"], flag_id, body.reviewer_id, body.note),
            )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/export/csv")
def export_csv():
    """Download all reviewed sessions as a CSV file."""
    date_str = datetime.now().strftime("%Y%m%d")

    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT s.session_id, s.overall_verdict, s.language_detected,
                       s.duration_minutes, s.session_type, s.review_status,
                       s.reviewer_id, s.reviewer_note, s.session_note,
                       COALESCE(fc.flag_count, 0) AS flag_count,
                       s.astrotalk_flagged, s.astrotalk_flag_category, s.reviewed_at
                FROM sessions s
                LEFT JOIN (
                    SELECT session_id, COUNT(*) AS flag_count
                    FROM flags GROUP BY session_id
                ) fc ON fc.session_id = s.session_id
                WHERE s.review_status != 'PENDING'
                ORDER BY s.reviewed_at DESC
            """).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    _HEADERS = [
        "session_id", "verdict", "language_detected", "duration_minutes",
        "session_type", "review_status", "reviewer_id", "reviewer_note",
        "session_note", "flag_count", "astrotalk_flagged",
        "astrotalk_flag_category", "reviewed_at",
    ]

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_HEADERS)
        for row in rows:
            rd = dict(row)
            writer.writerow([
                rd.get("session_id", ""),
                rd.get("overall_verdict", ""),
                rd.get("language_detected", ""),
                rd.get("duration_minutes", ""),
                rd.get("session_type", ""),
                rd.get("review_status", ""),
                rd.get("reviewer_id", ""),
                rd.get("reviewer_note", ""),
                rd.get("session_note", ""),
                rd.get("flag_count", 0),
                rd.get("astrotalk_flagged", ""),
                rd.get("astrotalk_flag_category", ""),
                rd.get("reviewed_at", ""),
            ])
        buf.seek(0)
        yield buf.read()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f"attachment; filename=gt_review_export_{date_str}.csv"
        },
    )
