# Deployment

## The constraint that shapes everything

**The backend cannot run on Vercel.** Three hard limits, not preferences:

| Vercel limit | This backend |
| --- | --- |
| 250 MB serverless bundle | torch 769 MB + scipy 109 MB + pandas 72 MB + sklearn 48 MB |
| Ephemeral filesystem | a 39 MB SQLite database holding nine years of history that must persist |
| 60 s (hobby) / 300 s (pro) execution | a structural research run takes 489 s |
| No long-lived process | APScheduler needs one |

So the deployment splits in two:

```
   Vercel                          Anywhere with a disk
   ┌──────────────────┐            ┌──────────────────────────┐
   │ Flutter web app  │  ──API──►  │ FastAPI + SQLite         │
   │ (static files)   │            │ Docker, persistent volume│
   └──────────────────┘            └──────────────────────────┘
```

The Flutter app is static output, which is exactly what Vercel is good at.
The backend needs a host that gives it a disk and a long-running process:
Fly.io, Railway, Render, or any VPS. The Docker image is built and smoke-tested
in CI and runs on all of them unchanged.

---

## 1. Backend

```bash
docker compose up -d --build
curl http://localhost:8100/api/health
```

Then fill it with data — the container starts empty:

```bash
docker compose exec app crypto-intel backfill
docker compose exec app crypto-intel research-structural
```

### Before exposing it

- **There is no authentication.** `docker-compose.yml` publishes on
  `127.0.0.1` deliberately. Put a reverse proxy with auth in front.
- **Mount a volume on `/app/data`**, or every rebuild starts from an empty
  database.
- **Set `CORS_ORIGINS` to the Vercel URL** once the app is deployed, e.g.
  `CORS_ORIGINS=https://crypto-intelligence.vercel.app`. Any other origin
  receives no CORS header and is refused by the browser.

---

## 2. Flutter app on Vercel

The repository root is safe to deploy directly to Vercel. The root
`vercel.json` builds the Flutter app in `app/` and publishes only `app/build/web`.
This prevents Vercel from trying to run the Python backend as a serverless
function.

If the Vercel project root is already set to `app/`, the same settings also
exist in `app/vercel.json`.

| Setting | Value |
| --- | --- |
| Root directory | repository root, or `app` |
| Build command | root: `cd app && bash vercel-build.sh`; app root: `bash vercel-build.sh` |
| Output directory | root: `app/build/web`; app root: `build/web` |
| Environment variable | `API_BASE_URL` = your backend URL |

`vercel-build.sh` fetches a pinned Flutter SDK, because Vercel's build image
has none. `API_BASE_URL` is compiled into the bundle at build time — changing
it requires a redeploy, not just an environment change.

Without `API_BASE_URL`, the app first calls its own origin. On Vercel that
returns the static app shell rather than JSON, so the Flutter client falls back
to the bundled snapshots in `app/assets/static_api/`.

Regenerate those snapshots from a running local backend with:

```bash
python scripts/export_flutter_static_api.py --base-url http://127.0.0.1:8100
```

That mode is useful for a read-only demo. For live market data, set
`API_BASE_URL` to a real backend and redeploy.

### Local equivalent

```bash
cd app
flutter build web --release --dart-define=API_BASE_URL=http://127.0.0.1:8100
```

---

## 3. Mobile builds

The same source builds for Android and iOS; only the define changes:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://your-backend
flutter build ipa --release --dart-define=API_BASE_URL=https://your-backend
```

A phone cannot reach `127.0.0.1` — that resolves to the phone itself. Use the
machine's LAN address or a deployed backend.

---

## What runs where

| Component | Host | Why |
| --- | --- | --- |
| Flutter web | Vercel | static files, global CDN |
| Flutter mobile | app stores / sideload | same codebase |
| FastAPI + SQLite | Fly.io / Railway / Render / VPS | needs a disk and long processes |
| Research runs | the backend host, via CLI | 8 minutes each; not a request |
| Scheduler | the backend host, `SCHEDULER_ENABLED=true` | needs a persistent process |

---

## Alternative: one origin, no Vercel

If splitting hosts is not worth it, the React frontend in `frontend/` is served
by FastAPI itself from the same origin, so `docker compose up` gives a complete
working app on one port with no CORS configuration at all. The Flutter app is
the better choice when you want it on a phone.
