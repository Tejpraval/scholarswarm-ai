# Deployment guide

The repository is a monorepo: deploy the FastAPI API on Render and the Vite frontend on Vercel. Demo Mode works without provider credentials. Live Research requires valid, quota-available Gemini and Tavily credentials.

## Render backend

The root `render.yaml` is a Blueprint for one Python web service. In Render, create a **New + → Blueprint** from the GitHub repository and approve the `scholarswarm-ai-api` service. Its settings are:

- Root directory: `backend`
- Python version: `3.12.11` (pinned in the repository `.python-version` and in `render.yaml`; if configuring the service manually, add `PYTHON_VERSION=3.12.11` in the Render dashboard too)
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/api/health`
- No persistent disk is required for the hackathon demo.
- `DB_PATH=scholarswarm.db`
- `UPLOAD_DIR=uploads`
- `FRONTEND_URL`: add this in the Render Environment dashboard after the frontend is deployed; use the Vercel origin with no trailing slash
- `GEMINI_API_KEY`, `TAVILY_API_KEY`: optional for Demo Mode; add replacement credentials in the Render Environment dashboard to enable Live Research
- `GEMINI_MODEL`: optional; the service default is used when omitted

This no-disk configuration is suitable for the hackathon demo. SQLite data and uploaded PDFs are stored under the service working directory and can be lost on restart or redeploy. For durable data, attach a paid Render disk mounted at `/var/data` and change both paths back to `/var/data/scholarswarm.db` and `/var/data/uploads`. A disk is single-instance; the application also keeps active SSE queues in process memory, so keep the API at one instance. Render only preserves files under the mounted path, and disk-backed deploys can briefly interrupt service.

After the first deploy, open `https://<render-service>.onrender.com/api/health` and confirm a 200 response before configuring Vercel. CORS will allow only local development origins until `FRONTEND_URL` is added.

## Vercel frontend

Create a Vercel project from the same GitHub repository, set **Root Directory** to `frontend`, and use:

- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable `VITE_API_URL`: `https://<render-service>.onrender.com/api`

The checked-in `frontend/vercel.json` rewrites browser routes to the Vite entry document. After the first frontend deploy, copy its public origin into Render's `FRONTEND_URL`, then redeploy the backend so CORS permits that origin. Keep `VITE_API_URL` set in Vercel Preview and Production environments as needed; it is a public endpoint, never a secret.

## Acceptance checks

Use Demo Mode first. Confirm the health endpoint, profile save/edit, valid and invalid PDF upload, SSE progress, the curated results and their official links, details, and the SOP draft. Then test Live Research only after setting new credentials with available quota. Live failures stay visible and never substitute fixture results.

The Vercel and Render dashboard actions require the account owner's authentication and approval. Do not put provider keys in Git, Vercel's `VITE_*` variables, a Git remote URL, or chat. Add provider credentials only to Render's secret environment settings.

## Five-minute demonstration

1. **0:00** Open the deployed frontend and identify Demo Mode as curated evidence, not live AI research.
2. **0:30** Load fictional Maya Iyer, edit and save the profile, then upload a valid PDF and show invalid-file rejection.
3. **1:30** Start the demo workflow and show SSE progress labelled as fixture processing.
4. **2:30** Show the single confirmed Sydney opportunity and explain why Auckland and DAAD are left uncertain.
5. **3:30** Open the official source and application links; explain the funding range, cycle deadline, and unknown coverage details.
6. **4:15** Open the SOP Draft and point out it uses the fictional profile facts.
7. **4:45** Clarify that Live Research is separate and requires replacement provider credentials with available quota; this demonstration did not call Gemini or Tavily.
