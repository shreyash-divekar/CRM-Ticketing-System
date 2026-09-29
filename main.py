from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "support_crm.db"))
STATUSES = {"Open", "In Progress", "Closed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
            note_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
        CREATE INDEX IF NOT EXISTS idx_notes_ticket ON notes(ticket_id);
        """)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Relay Support CRM", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class TicketCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: EmailStr
    subject: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5, max_length=10000)


class TicketUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=5000)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate):
    created = now_iso()
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO tickets (customer_name, customer_email, subject, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'Open', ?, ?)",
            (payload.customer_name.strip(), str(payload.customer_email).strip().lower(), payload.subject.strip(), payload.description.strip(), created, created),
        )
        ticket_id = f"TKT-{cursor.lastrowid:03d}"
        db.execute("UPDATE tickets SET ticket_id = ? WHERE id = ?", (ticket_id, cursor.lastrowid))
    return {"ticket_id": ticket_id, "created_at": created}


@app.get("/api/tickets")
def list_tickets(status: str | None = None, search: str | None = Query(default=None, max_length=200)):
    if status and status not in STATUSES:
        raise HTTPException(422, "Status must be Open, In Progress, or Closed")
    sql = "SELECT ticket_id, customer_name, customer_email, subject, description, status, created_at, updated_at FROM tickets"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if search and search.strip():
        term = f"%{search.strip()}%"
        clauses.append("(ticket_id LIKE ? OR customer_name LIKE ? OR customer_email LIKE ? OR subject LIKE ? OR description LIKE ?)")
        params.extend([term] * 5)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC, id DESC"
    with connect() as db:
        return [dict(row) for row in db.execute(sql, params).fetchall()]


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id.upper(),)).fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        result = dict(row)
        result.pop("id", None)
        result["notes"] = [dict(note) for note in db.execute("SELECT note_text, created_at FROM notes WHERE ticket_id = ? ORDER BY id DESC", (ticket_id.upper(),)).fetchall()]
        return result


@app.put("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: str, payload: TicketUpdate):
    ticket_id = ticket_id.upper()
    if payload.status is not None and payload.status not in STATUSES:
        raise HTTPException(422, "Status must be Open, In Progress, or Closed")
    updated = now_iso()
    with connect() as db:
        if not db.execute("SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone():
            raise HTTPException(404, "Ticket not found")
        if payload.status is not None:
            db.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?", (payload.status, updated, ticket_id))
        if payload.notes and payload.notes.strip():
            db.execute("INSERT INTO notes (ticket_id, note_text, created_at) VALUES (?, ?, ?)", (ticket_id, payload.notes.strip(), updated))
            db.execute("UPDATE tickets SET updated_at = ? WHERE ticket_id = ?", (updated, ticket_id))
        elif payload.status is None:
            raise HTTPException(422, "Provide a status or a note")
    return {"success": True, "updated_at": updated}
