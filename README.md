# Productivity Copilot (Agentic AI)

An agentic productivity assistant that can connect to Google Calendar, check free/busy, and schedule tasks intelligently.

## Prerequisites
- Docker Desktop

## Setup
1. Clone repo
2. Copy env template:
   ```bash
   cp .env.example .env

Create a Google OAuth client (Web App) and add redirect URI:

http://localhost:8000/auth/google/callback

Put your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET into .env

Run
docker compose up --build

Test

Health: http://localhost:8000/health

Swagger: http://localhost:8000/docs

Connect Google

Call GET /auth/google/start in Swagger

Open returned auth_url in browser

Then check GET /auth/google/status

Create test event

GET /calendar/test-create-event


---

## 4) Initialize git + first commit
From project root:

```bash
git init
git add .
git commit -m "Initial MVP: FastAPI + Postgres + Google OAuth + Calendar tools"

5) Create GitHub repo + push
Option A: Using GitHub website (simplest)

Go to GitHub → New repository

Name: productivity-copilot

Don’t add README (we already have it)

Copy the repo URL

Then run:

git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/productivity-copilot.git
git push -u origin main

6) One important safety check

Run this to ensure .env is NOT tracked:

git status
git ls-files | grep "\.env" || echo "✅ .env not tracked"


If it shows .env, tell me — we’ll remove it from git history safely.