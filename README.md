## Productivity Copilot (Agentic AI)

An agentic productivity assistant that connects to Google Calendar, plans goals with an LLM, schedules tasks intelligently, and (optionally) gives you daily AI check‑in calls.

### High‑level features
- **Goal planning**: Turn a natural‑language goal into a structured roadmap with milestones and tasks (with hand‑picked learning resources).
- **Smart scheduling**: Schedule tasks into your Google Calendar based on your free/busy windows and daily time budget.
- **Task tracking**: Persisted task records so the system can track progress over time.
- **Daily AI check‑ins (Twilio)**: Optional phone calls that check in on today’s tasks and log your progress.
- **REST API + frontend scaffold**: FastAPI backend with a `frontend` app (separate repo) wired via CORS for local dev.

---

## Prerequisites
- **Docker Desktop**
- **Python 3.11+** (if you want to run backend directly)
- A **Google Cloud project** with OAuth client (Web application)
- (Optional) **Twilio account** with a verified phone number
- (Optional) **OpenAI API key** (or compatible LLM provider)

---

## Environment variables

Copy the example file and fill in values:

```bash
cp .env.example .env
```

### Secrets you must supply yourself

| Variable | Required? | Where to get it |
| --- | --- | --- |
| `SESSION_SECRET` | **Yes** | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Signs the login cookie — leaving the default lets anyone forge a session. |
| `GOOGLE_CLIENT_ID` | **Yes** | Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → **Web application** |
| `GOOGLE_CLIENT_SECRET` | **Yes** | Same OAuth client as above |
| `OPENAI_API_KEY` | **Yes** | https://platform.openai.com/api-keys (billing must be enabled) |
| `TWILIO_ACCOUNT_SID` | Only for check‑in calls | https://console.twilio.com (dashboard) |
| `TWILIO_AUTH_TOKEN` | Only for check‑in calls | Same dashboard |
| `TWILIO_PHONE_NUMBER` | Only for check‑in calls | A **voice‑capable** Twilio number you own, E.164 format (`+14155551234`) |

Also enable the **Google Calendar API** for your Google Cloud project
(APIs & Services → Library → Google Calendar API → Enable), and add your own
Google account as a **test user** on the OAuth consent screen while the app is
in "Testing" mode — otherwise consent fails with `access_denied`.

### Settings you'll probably want to change

- `TIMEZONE` — IANA name, e.g. `Asia/Kolkata`. Defaults to `America/Phoenix`.
- `WORKDAY_START_HOUR` / `WORKDAY_END_HOUR` — the window tasks are scheduled into.
- `FRONTEND_URL` — where the OAuth callback redirects, and the allowed CORS origin.
- `DEV_MODE` — set `false` in production so cookies get the `Secure` flag.

After the backend is up, `GET http://localhost:8000/config-check` reports which
integrations it actually detected (no secret values are returned).

> **Safety note**: `.env` is already git‑ignored. Never commit real secrets.

---

## Google OAuth setup

Create a **Web application** OAuth client in Google Cloud and add this redirect URI:

```text
http://localhost:8000/auth/google/callback
```

Put the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

---

## Running with Docker (recommended)

From the project root:

```bash
docker compose up --build
```

This will:
- Start the **FastAPI backend** on `http://localhost:8000`
- Start **Postgres** for persistence

Health + docs:
- **Health check**: `http://localhost:8000/health`
- **Swagger/OpenAPI**: `http://localhost:8000/docs`

---

## Connecting Google Calendar

1. Go to `http://localhost:8000/docs`
2. Call `GET /auth/google/start`
3. Open the returned `auth_url` in your browser and complete the consent flow
4. Call `GET /auth/google/status` to confirm that tokens are stored
5. Optionally, test calendar integration with any demo/calendar endpoints exposed in the API.

The backend will automatically refresh calendar tokens when needed.

---

## Daily AI check‑in calls (Twilio)

1. Set up Twilio credentials in `.env`:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
2. Register your phone: `POST /tasks/register-phone` with
   `{"phone": "+14155551234", "preferred_checkin_hour": 9, "timezone": "Asia/Kolkata"}`.
   On a Twilio trial account the number must be **verified** in the console first.
3. Run the backend — the APScheduler job runs hourly on the hour and will:
   - Find users whose `preferred_checkin_hour` matches the current hour in their timezone
   - Skip anyone currently in a meeting (checked against Google Calendar)
   - Call them using Twilio and log the result

Trigger one manually with `POST /calls/trigger` (uses your session cookie —
no email in the URL, so it can only call *your* registered number).

### Interactive vs. speak-only calls

Twilio has to reach your server to hold a two-way conversation. With
`BACKEND_URL=http://localhost:8000` it can't, so calls fall back to
**speak-only** inline TwiML — the AI talks, but can't hear you.

For the full interactive flow, expose the backend and point `BACKEND_URL` at it:

```bash
ngrok http 8000
```

Then set `BACKEND_URL=https://<your-subdomain>.ngrok-free.app` in `.env` and
restart. The `/calls/*` webhooks verify Twilio's request signature, so they
reject anything not actually sent by Twilio.

Check the `calls` and `tasks` API routes (and DB tables) for persisted history.

---

## Frontend

A **Next.js 16** app (App Router, TypeScript, no CSS framework) lives in
`frontend/`.

```bash
cd frontend && npm install && npm run dev
```

Then open **http://localhost:3000**. Configuration is one variable —
`NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000` (see
`frontend/.env.example`).

| Route | What it does |
| --- | --- |
| `/` | Connect Google Calendar; reports any missing backend configuration |
| `/goals/new` | Conversational intake, then builds and books the roadmap |
| `/dashboard` | Tasks grouped by goal — tick off, skip, delete, sync |
| `/calendar` | Week view of everything Copilot booked |
| `/progress` | Streak, completion rate, 30-day history, status breakdown |
| `/checkins` | Call history, phone settings, "call me now" |

Notes for anyone working on it:

- Auth is the signed `pc_user` cookie, so **every** request goes through
  `lib/api.ts`, which sets `credentials: "include"`. A plain `fetch` will 401.
- The backend stores naive UTC timestamps. `lib/format.ts` appends the `Z`
  before parsing — without it the browser reads them as local and every task
  shifts by your UTC offset.
- Pages are client components because the session cookie lives in the browser;
  a server component can't forward it to a different origin.
- Rate limits surface as `429`; `ApiError` carries `retryAfterSeconds`.

---

## Database migrations

Schema is owned by **Alembic**, not by `create_all()`. The Docker entrypoint runs
migrations before the API starts, so `docker compose up` is all you normally need.

An existing database created by an older build is adopted automatically: the
bootstrap stamps the baseline revision instead of replaying it, so **no data is
lost**. Running it by hand:

```bash
cd backend && python scripts/migrate.py
```

After changing a model, generate a migration and commit it:

```bash
cd backend && alembic revision --autogenerate -m "what changed"
```

CI runs `alembic check` and fails if a model was changed without a migration.

---

## Running the tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest
```

They use SQLite and stub out Google, Twilio and OpenAI — no network, no keys, no
containers. GitHub Actions runs the same suite plus a migration round-trip
against real Postgres and a container smoke test.

---

## Task ↔ calendar sync

Moving or deleting an event in Google is otherwise invisible to the app, so
stored times go stale and check-in calls cite the wrong hour.

| Endpoint | What it does |
| --- | --- |
| `POST /tasks/sync` | Reconciles stored tasks against Google. Moved events update the stored time; deleted events unschedule the task without discarding it. |
| `PATCH /tasks/{id}/reschedule` | Moves a task, updating Google Calendar too. If Google rejects the change, the database is left untouched rather than recording a time that doesn't exist. |
| `DELETE /tasks/{id}` | Deletes the task and removes its calendar event. |

---

## Rate limits

The endpoints that spend money are throttled per user: goal planning
(10 / 5 min), chat (30 / min), transcription (15 / 5 min), check-in calls
(3 / 10 min). Exceeding one returns `429` with a `Retry-After` header. The
counters are in-process — move them to Redis if you run more than one container.

---

## Known limitations

- **Session cookies never expire server-side.** There's no revocation list; the
  cookie is valid for 30 days or until `SESSION_SECRET` changes.
- **Resource links are picked from a fixed allow-list** of base URLs in
  `backend/app/agents/planner.py` to stop the model inventing dead links.
- **The check-in scheduler elects a leader** via a Postgres advisory lock, so
  only one worker places calls. On SQLite there's no election — run one process.

---

## Suggested next steps

- **Polish the planner & scheduler**: tune prompts, task sizes, and daily time budgets based on your own usage.
- **Harden auth & security**: production OAuth settings, `DEV_MODE=false`, and HTTPS in front of the API.
- **Deploy**: containerize and deploy the stack (e.g. Fly.io, Railway, Render, or a small VPS) with a managed Postgres instance.
- **Iterate on the check‑in UX**: refine call scripts, add SMS / chat follow‑ups, and build richer analytics over completed / skipped tasks.