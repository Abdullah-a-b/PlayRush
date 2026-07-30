# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

PlayRush is a real-time multiplayer game platform (Arabic-first UI): a FastAPI + Socket.IO backend, a
static HTML/CSS/JS frontend, and an Android app that wraps the frontend via Capacitor. Code comments and
log messages throughout the backend are written in Arabic — match that style when editing existing files.

Repo layout:
- `Backend/` — FastAPI app + Socket.IO server (`app/`), one-off/data scripts (`scripts/`), deploy config
- `FrontEnd/` — static site (no bundler/framework), served as-is and also packaged into the Android app
- `android/` — Capacitor-generated Android project (mostly generated; edit `capacitor.config.json` at repo root instead of files under `android/` where possible)

## Commands

### Backend (from `Backend/`)
```bash
pip install -r requirements.txt        # deps (Python 3.12)
python run_dev.py                      # dev server, http://localhost:8000, reload on app/ changes
python run_prod.py                     # prod launcher; WORKERS=N for multi-worker (requires REDIS_URL)
```
Requires `Backend/.env` (copy from `.env.example`) with at minimum `DATABASE_URL` (PostgreSQL — SQLite is
not supported, `database.py` raises on startup otherwise) and `SECRET_KEY`.

There is no automated test suite (no pytest config/tests in `Backend/`). Manual scripts under
`Backend/scripts/` exist for specific checks, e.g.:
```bash
python scripts/check_ai.py       # verify Gemini API key/model load outside the server
python scripts/loadtest.py       # manual load test
python scripts/redis_check.py    # verify Redis connectivity
```
No linter/formatter is configured for either Backend or FrontEnd — match surrounding style.

### Frontend
Static files in `FrontEnd/` — serve with any static server (the app auto-detects the API origin, see
`FrontEnd/js/config.js`). No build step, no package manager for the frontend itself.

### Android / Capacitor (from repo root)
```bash
npm run cap:add:android    # npx cap add android
npm run cap:sync           # npx cap sync — copies FrontEnd/ into the Android project per capacitor.config.json
npm run cap:open:android   # opens the project in Android Studio
```

### Deployment
Backend deploys to Fly.io via `Backend/Dockerfile` + `Backend/fly.toml` (health check on `/health`,
`auto_stop_machines = false` because live WebSocket games must not be interrupted). `Backend/.azure/`
suggests an Azure App Service target also exists/existed — check `.azure/config` before assuming Fly is
the only target.

## Architecture

### Backend: FastAPI + Socket.IO mounted together
`app/main.py` builds one ASGI app that is both a FastAPI app (REST) and a Socket.IO server (`sio`),
mounted at `/socket.io`. Every route/domain is registered twice: once at its normal prefix (`/auth`,
`/shop`, `/career`, ...) for the web frontend, and again under `/api/v1/...` for the mobile app — same
routers, just double-mounted. When adding a new domain router, mount it both ways if mobile should see it.

Startup (in `lifespan()`) launches a set of **supervised background tasks** (cleanup jobs, Wikidata
importers per game, presence heartbeat, cluster subscriber, Telegram bot listener) — each wrapped so a
crash logs and auto-restarts rather than dying silently. Follow `_make_supervised_task` when adding new
background loops instead of a bare `asyncio.create_task`.

### Domain layout (`app/domains/<domain>/`)
Domains (`users`, `wallet`, `support`, `games`, `notifications`) generally follow a
`router.py` (HTTP endpoints) → `service.py` (business logic) → `repository.py`/`models.py` (SQLAlchemy)
layering. Socket.IO event handlers live separately from HTTP routers (see below) even for the same domain.

Models are SQLAlchemy `Base` subclasses; they only become known to `Base.metadata` (and thus
`create_all()`) once imported inside `register_models()` in `app/infrastructure/database.py` — new model
modules must be added there.

### Game framework (`app/domains/games/`)
`base.py` defines the framework every game is meant to use:
- `BaseGameState` — shared per-match state (`players`, `stage`, `state_version` for stale-event rejection).
  **Anything stored here must be JSON-serializable** (`to_dict`/`from_dict` are abstract and required) —
  no sockets, locks, or callbacks — because the design goal is moving match state into Redis without
  rewriting games (see `FRAMEWORK_GUIDE.md` in the same folder).
- `BaseGame` — abstract lifecycle a game implements (`create_state`, `on_player_join`, `on_player_action`,
  `on_player_leave`, `check_win_condition`, `calculate_rewards`) plus `broadcast`/`send_to_player` helpers.
- `GameRegistry` — decorator-based registry/factory (`@GameRegistry.register`); `core_manager.py` and
  matchmaking derive valid game modes from it instead of hardcoded if/else.

Each game lives in its own package (`huroof/`, `career/`, `bank/`, `whoami/`, `knowledge/`) with the same
internal shape: `game.py` (registers with `GameRegistry`), `engine.py` (the `*GameState` class,
resolved by convention — `core_manager._create_game_state` derives the state class name from the game
class name and imports it from `<package>.engine`), `events.py` (Socket.IO handlers for that game),
`helps.py`, `solo_bot.py` (single-player AI opponent). `huroof` predates the framework and is mid-migration
onto it — see the migration notes in `FRAMEWORK_GUIDE.md` before changing it.

Matchmaking/room state itself (`matchmaking_queue`, `rooms` dicts) lives in `core_manager.py`, currently
in-process memory (not yet migrated to Redis).

### Socket.IO event registration (`app/sockets/`, `app/domains/games/sockets/`)
Connection-level events (connect/disconnect, auth) are in `app/sockets/`; game-adjacent but
cross-cutting concerns (`lobby`, `matchmaking`, `room_events`, `social_handlers`) live in
`app/domains/games/sockets/`. Each module exposes a `register_*_events(sio)` function called explicitly
from `app/main.py` — there's no auto-discovery, so a new event module must be imported and registered there.

### Scaling model (single-worker by default, Redis-gated multi-worker)
Redis is optional (`app/infrastructure/redis_client.py`, `redis_enabled()`). Without it, everything runs
in one process/one worker. With `REDIS_URL` set and `WORKERS>1`:
- Socket.IO broadcast uses `AsyncRedisManager` so events cross workers.
- `app/core/cluster.py` patches room-event dispatch into an "owner worker" pattern: a room lives on
  whichever worker created it, and events arriving at another worker are forwarded to the owner.
- On Windows, `run_prod.py` uses one process per port (`MULTIPORT`) instead of uvicorn's `--workers`,
  because shared-socket multi-worker is unreliable on Windows.
A worker crash loses in-flight rooms (players must re-matchmake) — full match-state migration to Redis
is explicitly deferred (see comments in `run_prod.py`).

### Content generation / AI
Game question banks (career, bank, huroof, knowledge, whoami) are periodically refreshed from Wikidata by
per-game importer loops (`app/domains/games/importers/`), each independently scheduled via
`*_IMPORT_INTERVAL_DAYS` env vars. Gemini (`app/infrastructure/gemini_model.py`, `GEMINI_API_KEY`) is
optional and used as an AI judge for free-text answers and for `/ai-status`; when the key is absent or
Gemini is unreachable, judging falls back to a lenient mode rather than failing.

### Config & environment
`Backend/.env` (see `.env.example` for the full list) drives almost everything — DB, Redis, JWT secret,
Google OAuth, Telegram bot, Sentry, allowed CORS origins, per-game import intervals, and `ALLOW_SAME_IP`
(a dev-only flag, gated by `app/core/dev_mode.py`, that relaxes same-IP/same-session matchmaking
restrictions for local testing). `FRONTEND_URL`/`BACKEND_URL` are left blank for local/relative-path dev
and only set to real domains in production.

### Frontend structure
One HTML file per page/feature (`login.html`, `lobby.html`, `games/huroof.html`, ...) each paired with a
same-named JS file in `FrontEnd/js/` (or `FrontEnd/js/games/` for game pages) and CSS in `FrontEnd/css/` —
no shared framework, no module bundler. `FrontEnd/js/config.js` builds a global `CONFIG` object by
auto-detecting the backend origin: localhost/127.0.0.1 in dev, the LAN IP when opened from a phone over
WiFi, or `PROD_API_ORIGIN` in production or inside the packaged app (`window.Capacitor` detection). Update
`PROD_API_ORIGIN` there when the production domain changes — it's the single source of truth other JS
files read (`CONFIG.API_URL`, `CONFIG.WS_URL`).

### Security posture already in place
Rate limiting via `slowapi` (`app/core/limiter.py`), strict security headers + CSP on every response,
`ProxyHeadersMiddleware` for real client IPs behind Fly/Azure's proxy, image upload validation in
`app/core/content_filter.py`/Pillow-based checks, and an anti-cheat/anti-collusion layer
(`app/core/anticheat.py`, `app/domains/games/anti_collusion.py`) tracking suspicious match patterns
server-side rather than trusting client-reported outcomes. Keep new game logic consistent with this: never
trust client-submitted win/score data without server-side validation against `BaseGameState`.
