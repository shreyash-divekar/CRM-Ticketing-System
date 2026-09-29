# Relay Support CRM

A responsive customer support ticketing CRM built with Python, FastAPI, SQLite, and vanilla JavaScript.

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000. Interactive API documentation is available at `/docs`. SQLite creates `support_crm.db` in the project directory on first start.

## Included

- Create tickets with customer contact details, a subject, and description
- Search across ticket ID, customer, email, subject, and description
- Filter by Open, In Progress, and Closed
- Ticket detail view with status updates and an append-only notes timeline
- Responsive dashboard and REST API

## API

- `POST /api/tickets`
- `GET /api/tickets?status=Open&search=...`
- `GET /api/tickets/{ticket_id}`
- `PUT /api/tickets/{ticket_id}` with `{ "status": "In Progress", "notes": "..." }`

Deploy with any ASGI host using `uvicorn main:app --host 0.0.0.0 --port $PORT` and mount a persistent volume for the SQLite database. Set `DATABASE_PATH` to a file on that volume. For multi-instance production deployments, switch to a managed PostgreSQL database.

The repository includes a `Dockerfile` and Railway health check configuration. In Railway, create a volume for the service, mount it at `/data`, and set `DATABASE_PATH` to `/data/support_crm.db` so the SQLite database survives restarts. The volume must be attached before creating tickets you need to keep; data stored in the container filesystem is ephemeral.
