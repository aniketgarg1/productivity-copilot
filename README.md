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

The `frontend` directory is currently **empty** — the UI lives in a separate
repo and is not checked in here.

- The backend allows CORS from `FRONTEND_URL` (default `http://localhost:3000`),
  so a local dev UI can call the API.
- The UI must send credentials (`fetch(url, { credentials: "include" })`) —
  authentication is a signed `pc_user` cookie, so requests without it get a 401.
- After OAuth the backend redirects to `${FRONTEND_URL}/dashboard`.

To wire up a UI repo as a submodule:

```bash
git submodule add <frontend-repo-url> frontend
```

---

## Known limitations

- **No database migrations.** Tables are created with `create_all()` at startup,
  so changing a model won't alter an existing table. For a dev reset:
  `docker compose down -v && docker compose up --build`.
- **Session cookies never expire server-side.** There's no revocation list; the
  cookie is valid for 30 days or until `SESSION_SECRET` changes.
- **Resource links are picked from a fixed allow-list** of base URLs in
  `backend/app/agents/planner.py` to stop the model inventing dead links.

---

## Suggested next steps

- **Add Alembic** for real schema migrations before storing anything you care about.
- **Polish the planner & scheduler**: tune prompts, task sizes, and daily time budgets based on your own usage.
- **Harden auth & security**: production OAuth settings, `DEV_MODE=false`, and HTTPS in front of the API.
- **Deploy**: containerize and deploy the stack (e.g. Fly.io, Railway, Render, or a small VPS) with a managed Postgres instance.
- **Iterate on the check‑in UX**: refine call scripts, add SMS / chat follow‑ups, and build richer analytics over completed / skipped tasks.