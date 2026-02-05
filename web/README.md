# ProcureWatch Web UI

Minimal local web UI to manage watchlists and inspect preview/new items. No auth.

## Setup

```powershell
cd web
npm install
```

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` if needed (default: `http://127.0.0.1:8000`).

## Run

**Backend** (from project root):

```powershell
python -m uvicorn app.main:app --reload
```

**Frontend** (from `web` folder):

```powershell
cd web
npm run dev
```

Open http://localhost:5173 . Navigate to Watchlists to list, create, edit, delete watchlists and view Preview / New notices.

## Build

```powershell
npm run build
```

Output in `web/dist`. Serve with `npm run preview` or any static host.
