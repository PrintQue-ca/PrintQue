## Learned User Preferences

- All code changes must be backwards compatible and non-destructive to existing user data and setup; migrations should preserve or recover data, not silently wipe it.
- Tests must never read or write live user data under `~/PrintQueData`; the app and pytest should be safe to run at the same time.
- When implementing an attached plan: do not edit the plan file; use the existing todos (do not recreate them); mark each in progress and finish all before stopping.
- Prefer concise, direct answers when asked what changed or how something works.

## Learned Workspace Facts

- Monorepo layout: Python Flask API in `api/`, React/Vite UI in `app/`. Local dev from repo root: `pnpm run dev` (UI) and `pnpm run api` (Flask) via root `package.json` scripts.
- Persistent user data lives under `{DATA_DIR or home}/PrintQueData/` via `api/utils/paths.py` (JSON state files, `uploads/`, logs, migration backups).
- Backend uses Flask-SocketIO with `async_mode='threading'`; background threads that emit Socket.IO events should use `utils/socketio_emit.py` (`emit_status_update` / `safe_emit` with app context). OS-thread workers and native locks: `utils/threading_compat.py`, `spawn_os_thread` in `printer_utils.py`.
- Library catalog persists in `library.json`; print queue jobs in `queue.json` (`QUEUE_JOBS`). Distributor walks the queue front-to-back (`sent < quantity`); jobs snapshot library metadata and reference ejection presets by `ejection_code_id` (G-code resolved at runtime). On Bambu, `sent` increments only when MQTT reaches RUNNING/PRINTING, not on FTP upload or MQTT publish. Queue jobs may store `last_error` / `error_events` via `record_queue_job_error` in `library_queue.py`. Legacy `orders.json` is migrated on load.
- Bambu LAN prints: `upload_to_bambu` STORs to the FTP root (bare filename); MQTT `project_file` uses `file:///sdcard/<name>` via `paths_for_stor` (P1 maps root → SD). Never use `cache/` or `sdcard/` FTP prefixes. MQTT `reason: error string` is a generic firmware placeholder; richer detail is decoded in `bambu_errors.py` from `print_error` / HMS on status pushes.
- Ejection G-code preview is client-side (`app/src/lib/gcode-simulator.ts`); Bambu send path auto-appends `M400` when missing. Bambu ejection completes after the last `M400` ACK (`ejection_m400_pending` in `bambu_handler.py`). Ejection runs only when `count_incremented_for_current_job` is true (job reached RUNNING).
- Local CI expectations after edits: `ruff check api/` and `cd api && pytest` for Python; `cd app && npx tsc --noEmit` and `cd app && npm run test` for TypeScript.
