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

Key variables (see `.env.example` for the full list):

- **Google OAuth / Calendar**
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `BACKEND_URL` (usually `http://localhost:8000` in dev)
  - `DATABASE_URL` (default Postgres DSN used by Docker Compose)

- **LLM configuration**
  - `LLM_PROVIDER` (e.g. `openai`)
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL_MAIN`
  - `OPENAI_MODEL_CHEAP`

- **Twilio (daily check‑in calls, optional)**
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_PHONE_NUMBER` (E.164 format, e.g. `+1XXXXXXXXXX`)

- **Daily check‑in behavior**
  - `DAILY_CHECKIN_ENABLED=true|false`
  - `DAILY_CHECKIN_HOUR=9` (24‑hour clock, local time)

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
2. Set `DAILY_CHECKIN_ENABLED=true` and choose `DAILY_CHECKIN_HOUR`.
3. Run the backend (Docker or directly) — the APScheduler job will:
   - Find users with daily check‑ins enabled
   - Call them using Twilio
   - Log check‑in results and task progress.

Check the `calls` and `tasks` API routes (and DB tables) for persisted history.

---

## Frontend

The `frontend` directory is currently an embedded Git repository (treated like a submodule). It is versioned separately from this backend.

- To work on the UI, open the `frontend` repo directly and follow its README.
- The backend enables CORS for `http://localhost:3000`, so a local dev UI can call the FastAPI API.

If you prefer, you can convert `frontend` into a proper Git submodule later:

```bash
git rm --cached frontend
git submodule add <frontend-repo-url> frontend
```

---

## Suggested next steps

- **Polish the planner & scheduler**: tune prompts, task sizes, and daily time budgets based on your own usage.
- **Harden auth & security**: move from dev to production OAuth settings, lock allowed origins, and configure HTTPS in front of the API.
- **Deploy**: containerize and deploy the stack (e.g. Fly.io, Railway, Render, or a small VPS) with a managed Postgres instance.
- **Iterate on the check‑in UX**: refine call scripts, add SMS / chat follow‑ups, and build richer analytics over completed / skipped tasks.