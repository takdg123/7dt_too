# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The 7DT (7-Dimensional Telescope) ToO (Target-of-Opportunity) web app: a React frontend where users submit ToO observation requests, and a Flask backend that serves telescope status, schedules, and visibility data, plus a SQLite-backed table of ToO alerts. It is deployed on this machine at `https://proton.snu.ac.kr/too/`.

## Commands

Frontend (`frontend/`, Create React App):
- `npm start`: dev server. For local dev, switch `frontend/src/config.js` `API_BASE_URL` to `http://localhost:<port>` (prod value is `/too/`).
- `PUBLIC_URL=/too npm run build`: builds into `frontend/build/`. Without `PUBLIC_URL=/too` the assets point at `/static/...` and the live site loads a blank page. Flask serves this directly (`static_folder='../../frontend/build'`), so a rebuild is what deploys frontend changes.
- `npm test`: Jest via react-scripts. Run one test with `npm test -- -t "<name>"`. `App.test.js` is the unmodified CRA stub and does not reflect the real UI.

Backend (`backend/`, run from this directory so `.env` and `config.py` resolve):
- `python run.py --port 5002`: Flask dev server (debug, 0.0.0.0).
- Production: uWSGI (`wsgi.ini`, mounted at `/too`, unix socket `backend.sock`) under systemd `too.service`. The `alert-monitor.service` unit runs `app/alert_monitor.py`. Restart with `sudo systemctl restart too alert-monitor`. Logs go to `backend/too_backend.log`.
- `python app/backfill.py`: one-off migration of existing alert folders into the SQLite DB.
- There is no backend test suite or linter config.

## Architecture

**Backend (`backend/app/`)**
- `__init__.py`: `create_app()` factory. Loads `config.Config`, sets up Flask-Mail, CORS for `/too/api/*` from `proton.snu.ac.kr`, and registers the single blueprint in `routes.py`.
- `routes.py`: every endpoint lives here (`/api/...`). `/` serves `frontend/build/index.html` after replacing the `__CSP_NONCE__` and `__CSRF_TOKEN__` placeholders. State-changing routes use the `@csrf_protect` decorator. The token comes from the session and is sent as the `X-CSRF-Token` header (see `frontend/src/csrf.js`). Importing the module runs `init_db()`.
- `too_db.py`: SQLite layer for the ToO table (`TOO_DB_PATH`). Uses thread-local connections and a retry loop on `OperationalError` (the DB is shared by uWSGI workers and the alert monitor). Schema evolves through `ensure_column_exists`. Also builds rows and GCN circular templates from alert folders (`create_alert_from_folder`, `ref/gcn_template.txt`). File permissions matter: uWSGI runs as `www-data` and the monitor runs as `7dt` (see `fix_db_permissions`).
- `alert_monitor.py`: a watchdog daemon on `$SDT_DATA_FOLDER/alert/`. Each new alert folder becomes a DB row. It runs as a script, so it has an import fallback for that case.
- `add_page.py`: `WikiManager` creates and updates Wiki.js pages under `/ToO/<target>` through GraphQL on proton.snu.ac.kr. `_add_page.py` is an older function-based version.
- `utils.py`: coordinate normalization (sexagesimal and degrees) and parsing of datetimes and trigger times from folder names.
- ToO request flow (`/api/send_email`): writes the request JSON, emails it to the observation alert inbox, creates a wiki page, emails the requester a confirmation, then deletes the temp file.

**External dependencies outside the repo**: `supy` (`/home/7dt/script/supy`, which gives `supy.observer` and `supy.tiles` for staralt and tile calculations; it must be on `PYTHONPATH`) and the optional `/home/7dt/pipeline` `DatabaseHandler`. The live telescope data files (`multitelescopes.dict`, `DB_Program.ascii`, `weatherinfo.dict`, `filtinfo.dict`, the `specmode/` folders, alert folders) are read from `SDT_DATA_FOLDER` and `SDT_CONFIG_FOLDER`. The in-repo `backend/data/` copies are legacy and are being removed.

**Config**: `backend/.env` supplies `SDT_MAIL`, `SDT_SENDER`, `SDT_PASSWORD`, `SDT_ACCESS_PASSWORD` (the UI password gate, checked by `/api/validate-password`), `WIKI_API_TOKEN`, `TOO_DB_PATH`, `SDT_DATA_FOLDER`, and `SDT_CONFIG_FOLDER`.

**Frontend (`frontend/src/`)**: `App.js` has a password gate (`PasswordForm`) and MUI tabs for `StatusTable` (telescope and weather status), `DailyScheduleTable`, `TargetForm` (ToO request form with spec/deep mode, staralt chart via Chart.js, tile lookup), and `TooTable` (view and edit DB rows, GCN text, coordinates). All requests go through axios to `API_BASE_URL`.

## Gotchas

- Many tracked files (`config.py`, `run.py`, `wsgi.py`, TLS key and cert files) are also listed in `.gitignore`. Don't commit secrets, and check `git status` before staging broadly. `frontend/node_modules` and `frontend/build` are tracked as well.
- Paths are hardcoded to `/home/7dt/...` in several modules.
