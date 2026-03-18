```
╔══════════════════════════════╗
║  📦  D E P O T               ║
║  local project inventory     ║
╚══════════════════════════════╝
```

# Depot

**Depot** is a local project inventory dashboard — a Streamlit app that scans your project folders, indexes rich metadata, and gives you a fast, filterable command center for everything on your machine.

Stop wondering what's in that folder. Just open Depot.

> **100% local. No accounts. No telemetry. No cloud. Your data never leaves your machine.**

---

## Quick Start

```powershell
.\start.ps1
```

That's it. `start.ps1` handles everything: creates a `.venv` if needed, installs dependencies, and launches the dashboard in your browser. No manual setup required.

To stop the running server:

```powershell
.\stop.ps1
```

---

## Privacy

Depot is designed to be entirely offline:

- **No telemetry** — nothing is tracked or reported anywhere
- **No accounts** — no sign-in, no cloud sync, no API keys required
- **No network calls** — all scanning, indexing, and browsing is local
- **Your data is yours** — the SQLite database and `.repo-meta.json` files live on your machine and go nowhere
- **Read-only by default** — Depot never modifies your project files

---

## Features

### Inventory Table
- Unified view across **multiple scan roots** — mix drives, OneDrive folders, local dev dirs
- Sortable, filterable table with instant search
- Columns: Git presence, remote URL, last commit date/author, size (logical + allocated), language, framework, file/folder counts, errors, OneDrive state, status, tags, duplicates
- **Pinned projects** float to the top; **hidden projects** disappear from the main view

### Git Intelligence
- Detects `.git` presence and bare repos
- Pulls remote URL, last commit date, last commit author, and recent commit log
- Links remote URLs directly to GitHub/GitLab/Bitbucket in the browser
- Shows `☁️` for projects with a remote, `🌿` for local-only git repos

### Duplicate Detection
- Builds a **file signature** from sampled filenames and sizes
- Groups projects with matching signatures — flags likely copies, forks, or accidental duplicates
- Filter to show only duplicate groups or only unique projects

### OneDrive State Tracking
- Reads Windows file attributes to detect sync state per project:
  - `☁️ Cloud-only` — not downloaded locally
  - `📌 Pinned` — always kept on device
  - `🔄 Syncing`
  - Mixed states reported per-project

### File Explorer (in-app, read-only)
- Browse any project's folder tree without leaving the dashboard
- Click to preview: **text files, source code, images** rendered inline
- File icons for 50+ extensions
- **Open in Explorer** button to jump directly to any folder or file in Windows Explorer

### Ignored Folders
- Globally configure folders to skip during scanning (e.g. `node_modules`, `.venv`, `.next`, `__pycache__`)
- Ignored folders that exist inside a project are shown as **badges with tooltips** in the file explorer — you can see them without scanning them
- Managed from the sidebar — no config file editing required

### Live Preview Server
- Projects with an `index.html` get a **Launch Preview** button
- Depot spins up a local HTTP server and opens it in your browser — no config needed
- Stop the server from the same panel

### Package Panels
Deep-dive panels for recognized project types:
- `package.json` — name, version, description, scripts, dependencies
- `pyproject.toml` — project metadata, tool config
- `requirements.txt` — full dependency list
- `Cargo.toml` — Rust package info
- `go.mod` — Go module and dependencies

### README Cards
- Dedicated **READMEs** tab with a card grid across all projects
- Shows project name, README snippet, and status at a glance
- Great for reviewing what you have before starting something new

### Labels & Annotations
Annotate projects without touching your code — stored in `.repo-meta.json` inside each project folder:

| Field | Options |
|---|---|
| `status` | `active` / `wip` / `completed` / `archived` / `abandoned` / `template` |
| `tags` | custom, filterable |
| `pinned` | floats to top of table |
| `hidden` | removes from main view |
| `category` | group related projects |
| `description` | one-liner shown in table |
| `notes` | freeform notes |

Hidden/archived projects are accessible via the **🙈 Hidden** nav section.

### Configurable Scan
- Add/remove scan roots from the sidebar — point Depot at any folder on any drive
- Run a full rescan anytime — results saved to a local SQLite database

---

## Files

| File | Purpose |
|---|---|
| `depot.py` | Main Streamlit app |
| `start.ps1` | Launch script — sets up venv, installs deps, starts dashboard |
| `stop.ps1` | Kills the running Streamlit process |
| `depot_config.json` | Scan roots and ignored folders (auto-created on first run) |
| `depot.db` | SQLite project index (auto-created on first scan) |

---

## PowerShell Utilities

Standalone scripts — no Python required.

| Script | Purpose |
|---|---|
| `scan-folder-status.ps1` | Quick CLI scan — prints colored `[GIT]` / `[CODE]` / `[ASSET]` / `[EMPTY]` markers |
| `compare-folder-metrics.ps1` | Side-by-side comparison of two roots by name, size, file count, folder count |

```powershell
.\scan-folder-status.ps1 -RootPath "C:\Users\you\projects"
.\compare-folder-metrics.ps1 -LeftRoot "C:\Users\you\OneDrive\projects" -RightRoot "C:\Users\you\projects"
```

> If script execution is blocked: `powershell -NoProfile -ExecutionPolicy Bypass -File ".\start.ps1"`

---

## Requirements

- Python 3.10+
- Windows (OneDrive attribute detection is Windows-only; everything else works cross-platform)

Dependencies are installed automatically by `start.ps1`.

---

## Tips

- `.repo-meta.json` files can be committed alongside your projects — metadata travels with the repo
- Hidden projects are excluded from the main table but always accessible via **🙈 Hidden** in the nav
- `depot.db` and `depot_config.json` are local to your Depot install — add them to `.gitignore` if you fork this repo
