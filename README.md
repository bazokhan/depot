# Depot

**Depot** is a local project inventory dashboard — a read-only Streamlit app that scans your project folders, indexes metadata, and lets you annotate, filter, and navigate everything from one place.

## Features

- **Unified inventory** across multiple scan roots
- **Git metadata** — presence, remote URL, last commit date/author, recent commits
- **File metrics** — recursive file/folder counts, logical size, allocated disk size, OneDrive states
- **Language & framework detection** — top languages, framework hints, duplicate signature grouping
- **File explorer** — browse folders, preview text/code/images in-app (read-only)
- **Package panels** — `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`
- **README overview** — card grid with snippets across all projects
- **User metadata** (`🏷️ Labels & Notes`) — annotate projects without touching your code:
  - `hidden` — exclude from the main table
  - `pinned` — float to the top
  - `status` — active / wip / completed / archived / abandoned / template
  - `tags` — custom filterable tags
  - `category`, `description`, `notes`
- **Hidden view** — dedicated tab for hidden and archived projects
- Metadata stored in `.repo-meta.json` inside each project folder — portable, git-friendly, survives rescans

## Requirements

- Python 3.10+
- Windows (OneDrive attribute detection is Windows-only; rest works cross-platform)

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
streamlit run depot.py
```

Then:

1. Add your scan roots in the sidebar and click **Run Full Scan**.
2. Filter and browse the inventory table.
3. Click a row to open the project drilldown.
4. Use **🏷️ Labels & Notes** to annotate projects.

## Files

| File | Purpose |
|---|---|
| `depot.py` | Main Streamlit app |
| `depot_config.json` | Scan roots and ignored folders (auto-created) |
| `depot.db` | SQLite project index (auto-created on first scan) |

## PowerShell utilities

| Script | Purpose |
|---|---|
| `scan-folder-status.ps1` | Quick CLI scan — prints colored `[GIT]` / `[CODE]` / `[ASSET]` / `[EMPTY]` markers |
| `compare-folder-metrics.ps1` | Compares two root folders by name, size, file count, folder count |

### `scan-folder-status.ps1`

```powershell
.\scan-folder-status.ps1 -RootPath "D:\projects"
```

### `compare-folder-metrics.ps1`

```powershell
.\compare-folder-metrics.ps1 -LeftRoot "D:\OneDrive\projects" -RightRoot "D:\projects"
```

## Tips

- If script execution is blocked: `powershell -NoProfile -ExecutionPolicy Bypass -File ".\scan-folder-status.ps1"`
- Hidden projects are excluded from the main table but accessible via **🙈 Hidden** in the nav bar.
- `.repo-meta.json` files can be committed alongside your project if you want metadata to travel with the repo.
