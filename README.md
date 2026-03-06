# Folder Scan Utilities

This directory contains two PowerShell scripts for scanning/comparing project folders and one read-only web dashboard for manual review.

## Requirements

- Windows PowerShell 5.1+ or PowerShell 7+
- Python 3.10+ (recommended) for dashboard
- Read permission for scanned directories

## Scripts

### `scan-folder-status.ps1`

Recursively scans each immediate child folder of a root path and prints a colored table with markers.

#### What it marks

- `[GIT]`: Folder is a Git repository or contains a Git repository in its tree.
- `[CODE]`: Folder contains code files somewhere in its tree, but has no Git repository in that tree.
- `[ASSET]`: Folder contains image-like asset files in its tree.
- `[EMPTY]`: Folder tree contains no files at all (even if it has subfolders).

#### Usage

Default root is `D:\OneDrive\projects` if it exists; otherwise current folder:

```powershell
.\scan-folder-status.ps1
```

Run on a specific path:

```powershell
.\scan-folder-status.ps1 -RootPath "D:\OneDrive\projects"
```

#### Notes

- The script checks immediate child folders of the selected root.
- Statuses are not exclusive except for `CODE`, which is shown only when no Git repo exists in that folder tree.

---

### `compare-folder-metrics.ps1`

Compares immediate child folders between two root directories by folder name, recursively.

For matching names, it compares:

- Total size in bytes
- File count
- Folder count

Creation date and other timestamps are ignored.

#### Output status

- `[MATCH]`: Same folder name exists on both sides and all compared metrics are equal.
- `[DIFF]`: Same folder name exists on both sides but at least one metric differs.
- `[MISSING]`: Folder exists only on one side.

#### Usage

Default paths (`D:\OneDrive\projects` vs `D:\projects`):

```powershell
.\compare-folder-metrics.ps1
```

Custom paths:

```powershell
.\compare-folder-metrics.ps1 -LeftRoot "D:\OneDrive\projects" -RightRoot "D:\projects"
```

---

## Read-Only Web Dashboard

For deeper manual review, use the Streamlit dashboard:

- Script: `project_inventory_dashboard.py`
- Dependencies list: `requirements-dashboard.txt`
- Local database output: `project_inventory.db`

### What the dashboard gives you

- Unified inventory across `D:\OneDrive\projects` and `D:\projects`
- Project-level metadata:
  - Git presence in tree, remote URL, last commit date/author
  - Recursive file/folder counts
  - Logical size and allocated/on-disk size (where available)
  - OneDrive-related file state summary
  - Top languages, framework hints, duplicate signature grouping
- Read-only folder navigation and file preview:
  - Browse folders similar to Explorer
  - Preview text/code files and images in-app
  - No delete, move, or edit actions

### Setup

```powershell
python -m pip install -r ".\requirements-dashboard.txt"
```

### Run

```powershell
streamlit run ".\project_inventory_dashboard.py"
```

Then in the app:

1. Set roots (defaults are already set to your two folders).
2. Click **Run Full Scan**.
3. Filter/sort the inventory table.
4. Select a project and use the read-only explorer + preview panel.

### Notes about OneDrive accuracy

- `logical_size_bytes` is file logical length.
- `allocated_size_bytes` is physical allocated size where Windows reports it.
- `allocated_size_missing_files` indicates how many files could not be resolved for allocated-size calculation.
- OneDrive state flags are shown in `onedrive_states` to help identify cloud-only placeholders during manual review.

## Tips

- If script execution is blocked, run PowerShell as your user and use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scan-folder-status.ps1"
```

or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\compare-folder-metrics.ps1"
```

- Recursive scans can take time on large directory trees.
