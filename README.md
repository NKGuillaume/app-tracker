# Application Tracker

Connects to your Gmail via Google OAuth, detects job-application emails, extracts
structured data with OpenAI, and stores it in Supabase for a searchable dashboard.

## Repo layout

- `backend/` — FastAPI service (auth, Gmail sync, email extraction, applications API)
- `frontend/` — React + Vite dashboard
- `supabase/schema.sql` — database schema (run once against your Supabase project)

## External setup (do this first)

You need accounts/credentials from a few external services before anything will run.

1. **Google Cloud project**
   - Enable the **Gmail API**.
   - Configure the **OAuth consent screen** (External, Testing mode is fine to start; add
     yourself as a test user).
   - Create an **OAuth 2.0 Client ID** (Web application). Add authorized redirect URIs:
     - `http://localhost:8000/auth/callback` (local dev)
     - `https://<your-render-url>/auth/callback` (add this once you deploy, Phase D)
   - Note the **Client ID** and **Client Secret**.
2. **Google Cloud Pub/Sub** (only needed for Phase C, push notifications)
   - Create a topic (e.g. `gmail-push-notifications`).
   - Create a push subscription pointing at `https://<your-render-url>/sync/gmail-webhook`.
   - Grant the topic's **Pub/Sub Publisher** role to `gmail-api-push@system.gserviceaccount.com`.
3. **Supabase project**
   - Create a project at supabase.com.
   - Run `supabase/schema.sql` in the SQL editor.
   - Note the project URL and the **`service_role`** key (backend-only secret — never expose
     this to the frontend).
4. **OpenAI API key** — create one at platform.openai.com.
5. **Render account** (Phase D) — Web Service pointed at `backend/`.
6. **Vercel account** (Phase D) — project root `frontend/`.

## Local development

Two servers, run in separate terminals. Manual sync works fully locally — no tunnel
needed. Gmail push notifications (Pub/Sub) only work once deployed with a public URL.

### Backend

```
cd backend
cp .env.example .env   # fill in your values
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### Frontend

```
cd frontend
cp .env.example .env
npm install
npm run dev
```

The frontend expects the backend at `VITE_API_BASE_URL` (defaults to
`http://localhost:8000`) and the backend expects the frontend origin in
`FRONTEND_ORIGIN` for CORS + post-login redirect (defaults to `http://localhost:5173`).
