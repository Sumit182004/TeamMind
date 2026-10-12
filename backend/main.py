
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import hashlib
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query,Request
from pydantic import BaseModel, Field

from qdrant_memory import ensure_collection, save_memory, search_memories
from decision_workflow import run_decision_workflow
from decision_workflow import extract_decision_from_transcript

app = FastAPI(
    title="TeamMind API",
    description="Collaborative AI Decision Intelligence",
    version="0.4.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://team-mind-eta.vercel.app"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).resolve().parent / "teammind.db"


# DATABASE

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                problem TEXT NOT NULL,
                options TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                recommendation TEXT,
                created_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                output TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS omi_segments (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                speaker TEXT,
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS omi_session_analyses (
                session_id TEXT PRIMARY KEY,
                decision_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
            )
        """)

        connection.commit()


init_db()


# REQUEST SCHEMA 

class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    problem: str = Field(min_length=1, max_length=5000)
    options: list[str] = Field(min_length=2, max_length=10)


# HELPERS

def format_decision(row):
    decision = dict(row)
    decision["options"] = json.loads(decision["options"])
    return decision


def fetch_decision(decision_id: int):
    with closing(get_connection()) as connection:
        return connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()


def save_agent_run(decision_id: int, agent_name: str, output: str):
    with closing(get_connection()) as connection:
        connection.execute(
            """
            INSERT INTO agent_runs
                (decision_id, agent_name, status, output, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                agent_name,
                "completed",
                output,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()


# BASIC ROUTES 

@app.get("/")
def home():
    return {
        "project": "TeamMind",
        "status": "running",
        "message": "Think together. Challenge assumptions. Decide with confidence.",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


# DECISION ROUTES

@app.post("/api/decisions", status_code=201)
def create_decision(request: DecisionCreate):
    title = request.title.strip()
    problem = request.problem.strip()
    options = [option.strip() for option in request.options]

    if not title or not problem or any(not option for option in options):
        raise HTTPException(
            status_code=422,
            detail="Title, problem, and options cannot be empty.",
        )

    created_at = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO decisions
                (title, problem, options, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, problem, json.dumps(options), "pending", created_at),
        )
        connection.commit()
        decision_id = cursor.lastrowid

        row = connection.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()

    decision = format_decision(row)
    related_memories = []
    memory_saved = False

    try:
        ensure_collection()
        related_memories = search_memories(
            f"{title}. {problem}. Options: {'; '.join(options)}",
            limit=3,
        )

        save_memory(
            text=(
                f"Decision request: {title}. Problem: {problem}. "
                f"Options: {'; '.join(options)}"
            ),
            metadata={
                "decision_id": decision_id,
                "memory_type": "decision_request",
                "topic": title,
                "created_at": created_at,
            },
        )
        memory_saved = True
    except Exception as exc:
        print(f"Qdrant memory warning: {exc}")

    return {
        **decision,
        "related_memories": related_memories,
        "memory_saved": memory_saved,
    }


@app.get("/api/decisions")
def list_decisions():
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM decisions ORDER BY id DESC"
        ).fetchall()

    return [format_decision(row) for row in rows]


@app.get("/api/decisions/{decision_id}")
def get_decision(decision_id: int):
    row = fetch_decision(decision_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found.")

    return format_decision(row)


# RUN MULTI-AGENT WORKFLOW

@app.post("/api/decisions/{decision_id}/run")
def run_decision(decision_id: int):
    row = fetch_decision(decision_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found.")

    decision = format_decision(row)

    with closing(get_connection()) as connection:
        connection.execute(
            "UPDATE decisions SET status = ? WHERE id = ?",
            ("running", decision_id),
        )
        connection.commit()

    try:
        ensure_collection()

        memories = search_memories(
            f"{decision['title']}. {decision['problem']}. "
            f"Options: {'; '.join(decision['options'])}",
            limit=10,
        )

        outputs = run_decision_workflow(
            title=decision["title"],
            problem=decision["problem"],
            options=decision["options"],
            memories=memories,
        )

        # Persist each agent's output.
        for agent_name, output in outputs.items():
            save_agent_run(
                decision_id=decision_id,
                agent_name=agent_name,
                output=output,
            )

        report = outputs["report"]

        with closing(get_connection()) as connection:
            connection.execute(
                """
                UPDATE decisions
                SET status = ?, recommendation = ?
                WHERE id = ?
                """,
                ("completed", report, decision_id),
            )
            connection.commit()

        # Save the completed result as a separate semantic memory.
        try:
            save_memory(
                text=(
                    f"Completed decision: {decision['title']}. "
                    f"Problem: {decision['problem']}. "
                    f"Options: {'; '.join(decision['options'])}. "
                    f"Final report: {report}"
                ),
                metadata={
                    "decision_id": decision_id,
                    "memory_type": "completed_decision",
                    "topic": decision["title"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            print(f"Could not save completed decision memory: {exc}")

        return {
            "decision_id": decision_id,
            "status": "completed",
            "agent_outputs": outputs,
            "message": "TeamMind decision workflow completed.",
        }

    except Exception as exc:
        with closing(get_connection()) as connection:
            connection.execute(
                "UPDATE decisions SET status = ? WHERE id = ?",
                ("failed", decision_id),
            )
            connection.commit()

        print(f"Decision workflow failed: {exc}")
        raise HTTPException(
            status_code=502,
            detail=(
                "The decision workflow failed. Check the backend terminal "
                "for the underlying Lyzr or Qdrant error."
            ),
        )


# DECISION REPORT

@app.get("/api/decisions/{decision_id}/report")
def get_decision_report(decision_id: int):
    row = fetch_decision(decision_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found.")

    with closing(get_connection()) as connection:
        agent_rows = connection.execute(
            """
            SELECT agent_name, status, output, created_at
            FROM agent_runs
            WHERE decision_id = ?
            ORDER BY id ASC
            """,
            (decision_id,),
        ).fetchall()

    return {
        "decision": format_decision(row),
        "agent_runs": [
            {
                **dict(agent_row),
                "output": agent_row["output"],
            }
            for agent_row in agent_rows
        ],
    }


# QDRANT MEMORY SEARCH

@app.get("/api/memory/search")
def memory_search(q: str = Query(min_length=3), limit: int = 3):
    if not 1 <= limit <= 10:
        raise HTTPException(
            status_code=422,
            detail="Limit must be between 1 and 10.",
        )

    try:
        ensure_collection()
        results = search_memories(q, limit=limit)
        return {
            "query": q,
            "count": len(results),
            "memories": results,
        }
    except Exception as exc:
        print(f"Qdrant search failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Memory search is unavailable. Check the Qdrant connection.",
        )
    

class TranscriptRequest(BaseModel):
    transcript: str = Field(min_length=10, max_length=30000)
    source: str = "omi"
class SourceTranscriptRequest(BaseModel):
    transcript: str = Field(min_length=10, max_length=30000)
    source: str = "omi"

@app.post("/api/omi/transcript")
def receive_omi_transcript(payload: TranscriptRequest):
    """Convert an Omi transcript into a saved TeamMind decision."""

    transcript = payload.transcript.strip()

    if len(transcript) < 10:
        raise HTTPException(
            status_code=400,
            detail="Transcript is too short.",
        )

    try:
        extracted = extract_decision_from_transcript(transcript)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    title = extracted["title"]
    problem = extracted["problem"]
    options = extracted["options"]

    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO decisions
                    (title, problem, options, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    title,
                    problem,
                    json.dumps(options),
                    "pending",
                    created_at,
                ),
            )

            decision_id = cursor.lastrowid
            conn.commit()

            cursor.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,),
            )
            row = cursor.fetchone()

            decision = format_decision(row)

    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not save the extracted decision.",
        ) from exc

    related_memories = []
    memory_saved = False

    try:
        ensure_collection()

        memory_query = (
            f"Decision request: {title}. "
            f"Problem: {problem}. "
            f"Options: {'; '.join(options)}. "
            f"Original voice transcript: {transcript}"
        )

        related_memories = search_memories(memory_query, limit=3)

        save_memory(
            text=memory_query,
            metadata={
                "decision_id": decision["id"],
                "memory_type": "omi_decision_request",
                "topic": title,
                "source": payload.source,
                "created_at": created_at,
            },
        )

        memory_saved = True

    except Exception as exc:
        print(f"Omi Qdrant memory warning: {exc}")

    return {
        "status": "created",
        "source": payload.source,
        "decision": decision,
        "related_memories": related_memories,
        "memory_saved": memory_saved,
        "next_action": {
            "label": "Run Decision Stress Test",
            "endpoint": f"/api/decisions/{decision['id']}/run",
            "method": "POST",
        },
        "message": (
            "Transcript converted into a TeamMind decision. "
            "The multi-agent workflow has not been started yet."
        ),
    }


@app.post("/api/omi/extract")
def extract_omi_transcript(payload: TranscriptRequest):
    """Extract a decision from a transcript without saving it."""
    transcript = payload.transcript.strip()

    if len(transcript) < 10:
        raise HTTPException(
            status_code=400,
            detail="Transcript is too short."
        )

    try:
        extracted = extract_decision_from_transcript(transcript)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc)
        ) from exc

    return {
        "status": "extracted",
        "source": payload.source,
        "title": extracted["title"],
        "problem": extracted["problem"],
        "options": extracted["options"],
        "message": "Review and edit the extracted decision before saving."
    }
@app.post("/api/decisions/{decision_id}/source-transcript")
def save_decision_source_transcript(
    decision_id: int,
    request: SourceTranscriptRequest,
):
    transcript = request.transcript.strip()

    if len(transcript) < 10:
        raise HTTPException(
            status_code=400,
            detail="Transcript must contain at least 10 characters.",
        )

    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        decision = connection.execute(
            "SELECT id, title, problem FROM decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found.")

    memory_text = (
        f"Original Omi conversation for decision: {decision['title']}\n"
        f"Decision problem: {decision['problem']}\n"
        f"Original transcript:\n{transcript}"
    )

    try:
        save_memory(
            memory_text,
            {
                "decision_id": decision_id,
                "memory_type": "omi_source_transcript",
                "source": request.source,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not save transcript to Qdrant: {exc}",
        ) from exc

    return {
        "status": "saved",
        "decision_id": decision_id,
        "message": "Original transcript saved to Qdrant.",
    }
# Omi webhook handling.
# Omi may reuse its top-level session_id across multiple recordings.
# The supplied payload includes speaker_id_scope in the form "<recording-id>:<speaker-id>".
@app.post("/api/omi/webhook")
async def omi_webhook(request: Request):
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON received from Omi.",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail="Expected an Omi webhook JSON object.",
        )

    provider_session_id = str(data.get("session_id") or "omi")
    segments = data.get("segments") or []

    if not isinstance(segments, list):
        raise HTTPException(
            status_code=400,
            detail="Omi webhook 'segments' must be a list.",
        )

    # Separate segments by recording scope, not by the reused provider session ID.
    grouped_segments = {}
    for segment in segments:
        if not isinstance(segment, dict):
            continue

        segment_text = str(segment.get("text") or "").strip()
        segment_id = segment.get("id")
        if not segment_text or not segment_id:
            continue

        speaker_scope = str(segment.get("speaker_id_scope") or "").strip()
        recording_id = speaker_scope.split(":", 1)[0] if speaker_scope else ""

        # The payload's recording scope is the conversation boundary.
        # Keep a fallback for payloads that do not include this field.
        local_session_id = (
            f"{provider_session_id}__{recording_id}"
            if recording_id
            else provider_session_id
        )

        grouped_segments.setdefault(local_session_id, []).append({
            "id": str(segment_id),
            "text": segment_text,
            "speaker": str(segment.get("speaker") or "unknown"),
            "recording_id": recording_id or None,
        })

    if not grouped_segments:
        return {
            "status": "received",
            "session_id": provider_session_id,
            "segments_saved": 0,
            "memory_saved": False,
            "message": "No transcript segments with IDs were present.",
        }

    now_text = datetime.now(timezone.utc).isoformat()
    saved_count = 0
    saved_session_ids = []
    memory_saved_any = False

    try:
        with closing(get_connection()) as connection:
            for local_session_id, session_segments in grouped_segments.items():
                newly_saved = []

                for segment in session_segments:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO omi_segments
                            (id, session_id, transcript, speaker, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            segment["id"],
                            local_session_id,
                            segment["text"],
                            segment["speaker"],
                            now_text,
                        ),
                    )
                    if cursor.rowcount == 1:
                        newly_saved.append(segment)

                if not newly_saved:
                    continue

                saved_count += len(newly_saved)
                saved_session_ids.append(local_session_id)

                # Save only newly received text. SQLite remains the source of truth.
                transcript = " ".join(item["text"] for item in newly_saved).strip()
                if len(transcript) >= 10:
                    try:
                        ensure_collection()
                        save_memory(
                            text=transcript,
                            metadata={
                                "memory_type": "omi_live_transcript",
                                "source": "omi",
                                "session_id": local_session_id,
                                "provider_session_id": provider_session_id,
                                "recording_id": newly_saved[0]["recording_id"],
                                "segment_ids": [item["id"] for item in newly_saved],
                                "speakers": sorted({
                                    item["speaker"] for item in newly_saved
                                }),
                                "created_at": now_text,
                            },
                        )
                        memory_saved_any = True
                    except Exception as exc:
                        # A Qdrant failure should not discard the SQLite transcript.
                        print(f"Omi Qdrant memory warning: {exc}")

            connection.commit()

    except sqlite3.Error as exc:
        print(f"Omi SQLite persistence error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not persist Omi transcript segments.",
        ) from exc

    print(
        f"Omi webhook: provider_session={provider_session_id}, "
        f"local_sessions={saved_session_ids}, segments_saved={saved_count}"
    )

    return {
        "status": "saved",
        "provider_session_id": provider_session_id,
        "session_ids": saved_session_ids,
        "segments_saved": saved_count,
        "memory_saved": memory_saved_any,
    }


class OmiAnalyzeRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1, max_length=500)


@app.get("/api/omi/session/{session_id}/segments")
def get_omi_session_segments(session_id: str):
    """Return individual transcript segments so the user can choose exactly what to analyze."""
    try:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id, transcript, speaker, created_at
                FROM omi_segments
                WHERE session_id = ?
                ORDER BY rowid ASC
                """,
                (session_id,),
            ).fetchall()
        return {
            "session_id": session_id,
            "segments": [dict(row) for row in rows],
        }
    except sqlite3.Error as exc:
        print(f"Could not load Omi segments: {exc}")
        raise HTTPException(status_code=500, detail="Could not load transcript segments.") from exc


@app.post("/api/omi/session/{session_id}/analyze")
def analyze_omi_session(session_id: str, payload: OmiAnalyzeRequest):
    """Analyze only the explicitly selected Omi transcript segments."""
    selected_ids = list(dict.fromkeys(str(value) for value in payload.segment_ids if str(value).strip()))
    if not selected_ids:
        raise HTTPException(status_code=422, detail="Select at least one transcript segment.")

    # Scope the idempotency key to this exact selection, not the whole recording.
    selection_hash = hashlib.sha256("\n".join(sorted(selected_ids)).encode("utf-8")).hexdigest()[:20]
    analysis_key = f"{session_id}::selection::{selection_hash}"

    with closing(get_connection()) as connection:
        existing = connection.execute(
            """
            SELECT d.* FROM omi_session_analyses a
            JOIN decisions d ON d.id = a.decision_id
            WHERE a.session_id = ?
            """,
            (analysis_key,),
        ).fetchone()
        if existing:
            decision = format_decision(existing)
            return {
                "status": "already_analyzed", "decision_id": decision["id"],
                "session_id": session_id, "title": decision["title"],
                "problem": decision["problem"], "options": decision["options"],
                "transcript": "", "workflow": {
                    "decision_id": decision["id"], "status": decision["status"],
                    "agent_outputs": {}, "message": "Returning the existing decision for this exact selection."
                },
                "message": "This exact transcript selection was already analyzed.",
            }

        placeholders = ",".join("?" for _ in selected_ids)
        rows = connection.execute(
            f"SELECT id, transcript, speaker FROM omi_segments WHERE session_id = ? AND id IN ({placeholders}) ORDER BY rowid ASC",
            [session_id, *selected_ids],
        ).fetchall()

    if len(rows) != len(selected_ids):
        found_ids = {row["id"] for row in rows}
        missing = [segment_id for segment_id in selected_ids if segment_id not in found_ids]
        raise HTTPException(
            status_code=422,
            detail="Some selected segments do not belong to this session or no longer exist. Refresh the transcript and select again.",
        )

    transcript = " ".join(row["transcript"].strip() for row in rows if row["transcript"].strip()).strip()
    if len(transcript) < 10:
        raise HTTPException(status_code=400, detail="The selected transcript is too short to analyze. Select more relevant segments.")

    try:
        extracted = extract_decision_from_transcript(transcript)
    except Exception as exc:
        print(f"Omi selected transcript extraction failed: {exc}")
        raise HTTPException(status_code=502, detail="Decision extraction failed. Check the backend terminal.") from exc

    title, problem, options = extracted["title"], extracted["problem"], extracted["options"]
    if len(options) < 2:
        raise HTTPException(status_code=422, detail="A decision needs at least two options. Select transcript segments that include the decision and alternatives.")

    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                "INSERT INTO decisions (title, problem, options, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, problem, json.dumps(options), "pending", created_at),
            )
            connection.commit()
            decision_id = cursor.lastrowid
    except sqlite3.Error as exc:
        print(f"Could not save Omi decision: {exc}")
        raise HTTPException(status_code=500, detail="Could not save the extracted decision.") from exc

    try:
        ensure_collection()
        save_memory(
            text=(f"Omi selected discussion: {title}. Problem: {problem}. Options: {'; '.join(options)}. Selected transcript: {transcript}"),
            metadata={
                "memory_type": "omi_selected_discussion", "source": "omi",
                "session_id": session_id, "analysis_key": analysis_key,
                "decision_id": decision_id, "topic": title,
                "selected_segment_ids": selected_ids, "created_at": created_at,
            },
        )
    except Exception as exc:
        print(f"Could not save selected Omi discussion memory: {exc}")

    workflow_result = run_decision(decision_id)
    with closing(get_connection()) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO omi_session_analyses (session_id, decision_id, created_at) VALUES (?, ?, ?)",
            (analysis_key, decision_id, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()

    return {
        "status": "completed", "decision_id": decision_id,
        "session_id": session_id, "title": title, "problem": problem,
        "options": options, "transcript": transcript,
        "selected_segment_ids": selected_ids, "workflow": workflow_result,
        "message": "Selected Omi discussion analyzed; unrelated segments were excluded.",
    }


@app.get("/api/omi/sessions")
def get_omi_sessions():
    """Return recent Omi conversations saved in SQLite."""
    try:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    MIN(created_at) AS started_at,
                    MAX(created_at) AS last_seen,
                    COUNT(*) AS segment_count
                FROM omi_segments
                GROUP BY session_id
                ORDER BY last_seen DESC
                LIMIT 20
                """
            ).fetchall()

            sessions = []

            for row in rows:
                transcript_rows = connection.execute(
                    """
                    SELECT transcript
                    FROM omi_segments
                    WHERE session_id = ?
                    ORDER BY rowid
                    """,
                    (row["session_id"],),
                ).fetchall()

                sessions.append({
                    "session_id": row["session_id"],
                    "started_at": row["started_at"],
                    "last_seen": row["last_seen"],
                    "segment_count": row["segment_count"],
                    "transcript": " ".join(
                        item["transcript"] for item in transcript_rows
                    ),
                })

        return {"sessions": sessions}

    except sqlite3.Error as exc:
        print(f"Omi sessions query error: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not load Omi conversations.",
        ) from exc
