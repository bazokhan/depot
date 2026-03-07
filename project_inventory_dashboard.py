import ctypes
import hashlib
import json
import os
import socket
import sqlite3
import stat
import subprocess
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).with_name("project_inventory.db")
CONFIG_PATH = Path(__file__).with_name("project_inventory_config.json")

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".log",
    ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh",
    ".rst", ".xml", ".env", ".htaccess", ".gitignore", ".dockerignore", ".editorconfig",
    ".bat", ".cmd", ".lock",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".ipynb": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".c": "C", ".h": "C/C++", ".cpp": "C++", ".hpp": "C++", ".cs": "C#", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".m": "Objective-C", ".r": "R", ".dart": "Dart",
    ".lua": "Lua", ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "SASS", ".sql": "SQL",
    ".ps1": "PowerShell", ".sh": "Shell",
}

MARKER_FILES = {
    "package.json": "Node/JS",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "Pipfile": "Python",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Gradle",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "pubspec.yaml": "Dart/Flutter",
    "next.config.js": "Next.js",
    "angular.json": "Angular",
    "vite.config.js": "Vite",
}

FILE_ICONS: Dict[str, str] = {
    ".py": "🐍", ".ipynb": "🐍",
    ".js": "📜", ".jsx": "⚛️", ".mjs": "📜", ".cjs": "📜",
    ".ts": "📘", ".tsx": "⚛️",
    ".json": "📋", ".jsonc": "📋",
    ".yaml": "⚙️", ".yml": "⚙️",
    ".toml": "⚙️", ".ini": "⚙️", ".cfg": "⚙️", ".conf": "⚙️",
    ".md": "📝", ".mdx": "📝", ".txt": "📄", ".rst": "📄",
    ".html": "🌐", ".htm": "🌐",
    ".css": "🎨", ".scss": "🎨", ".sass": "🎨", ".less": "🎨",
    ".env": "🔐", ".env.local": "🔐", ".env.example": "🔐",
    ".sh": "⚡", ".bash": "⚡", ".zsh": "⚡", ".bat": "⚡", ".cmd": "⚡", ".ps1": "⚡",
    ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️",
    ".svg": "🎭", ".ico": "🖼️", ".webp": "🖼️", ".bmp": "🖼️",
    ".mp4": "🎬", ".mov": "🎬", ".avi": "🎬", ".webm": "🎬",
    ".mp3": "🎵", ".wav": "🎵", ".ogg": "🎵",
    ".pdf": "📕", ".docx": "📘", ".doc": "📘", ".xlsx": "📗", ".xls": "📗", ".pptx": "📙",
    ".zip": "🗜️", ".tar": "🗜️", ".gz": "🗜️", ".7z": "🗜️", ".rar": "🗜️",
    ".sql": "🗄️", ".db": "🗄️", ".sqlite": "🗄️", ".sqlite3": "🗄️",
    ".rs": "🦀", ".go": "🔵", ".java": "☕", ".kt": "☕",
    ".cpp": "⚙️", ".c": "⚙️", ".h": "⚙️", ".hpp": "⚙️",
    ".cs": "💜", ".rb": "💎", ".php": "🐘", ".dart": "🎯", ".swift": "🍎",
    ".lock": "🔒",
    ".gitignore": "🚫", ".dockerignore": "🚫",
    ".xml": "📋", ".plist": "📋",
}
FOLDER_ICON = "📁"
DEFAULT_FILE_ICON = "📄"

FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_PINNED = 0x00080000
FILE_ATTRIBUTE_UNPINNED = 0x00100000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


# ---------------------------------------------------------------------------
# Generic utilities
# ---------------------------------------------------------------------------

def format_bytes(num: Optional[int]) -> str:
    if num is None:
        return "-"
    value = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num} B"


def bool_icon(value: int, yes: str = "✅", no: str = "—") -> str:
    return yes if int(value) == 1 else no


def path_to_file_url(path: str) -> str:
    normalized = path.replace("\\", "/")
    return f"file:///{quote(normalized, safe='/:')}"


def remote_to_web_url(remote_url: Optional[str]) -> Optional[str]:
    if not remote_url:
        return None
    raw = remote_url.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw[:-4] if raw.endswith(".git") else raw
    if raw.startswith("git@") and ":" in raw:
        host_part, repo_part = raw.split(":", 1)
        host = host_part.replace("git@", "").strip("/")
        repo = repo_part.strip("/")
        if repo.endswith(".git"):
            repo = repo[:-4]
        if host and repo:
            return f"https://{host}/{repo}"
    return None


def open_in_explorer(path: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        st.warning(f"Could not open path: {exc}")


def pick_folder(initial_dir: str = r"D:\\") -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=initial_dir or r"D:\\")
        root.destroy()
        return selected if selected else None
    except Exception:
        return None


def file_state_from_attrs(attrs: int) -> str:
    flags = []
    if attrs & FILE_ATTRIBUTE_OFFLINE:
        flags.append("offline")
    if attrs & FILE_ATTRIBUTE_PINNED:
        flags.append("pinned")
    if attrs & FILE_ATTRIBUTE_UNPINNED:
        flags.append("unpinned")
    if attrs & FILE_ATTRIBUTE_RECALL_ON_OPEN:
        flags.append("recall-on-open")
    if attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS:
        flags.append("recall-on-data")
    return ",".join(flags) if flags else "local"


def get_allocated_size(path: str) -> Optional[int]:
    if os.name != "nt":
        return None
    try:
        high = ctypes.c_ulong(0)
        ctypes.set_last_error(0)
        low = ctypes.windll.kernel32.GetCompressedFileSizeW(ctypes.c_wchar_p(path), ctypes.byref(high))
        if low == 0xFFFFFFFF:
            err = ctypes.get_last_error()
            if err != 0:
                return None
        return (high.value << 32) + low
    except Exception:
        return None


def run_git(project_path: str, args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", project_path] + args,
            capture_output=True, text=True, timeout=6, check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


def parse_remote_owner(remote_url: Optional[str]) -> Optional[str]:
    if not remote_url:
        return None
    url = remote_url.strip()
    if "github.com" in url or "gitlab.com" in url or "bitbucket.org" in url:
        cleaned = url.replace(".git", "").replace(":", "/")
        parts = cleaned.split("/")
        if len(parts) >= 2:
            return parts[-2]
    return None


def infer_frameworks(marker_hits: List[str]) -> str:
    frameworks = []
    for marker in marker_hits:
        hint = MARKER_FILES.get(marker)
        if hint and hint not in frameworks:
            frameworks.append(hint)
    return ", ".join(frameworks[:4])


def build_signature(file_samples: List[Tuple[str, int]]) -> str:
    digest = hashlib.sha256()
    for relative_path, file_size in sorted(file_samples):
        digest.update(relative_path.encode("utf-8", errors="ignore"))
        digest.update(b"\x00")
        digest.update(str(file_size).encode("ascii"))
        digest.update(b"\x00")
    return digest.hexdigest()


def get_file_icon(filename: str) -> str:
    name_lower = filename.lower()
    if name_lower in ("dockerfile",):
        return "🐳"
    suffix = Path(filename).suffix.lower()
    return FILE_ICONS.get(suffix, DEFAULT_FILE_ICON)


# ---------------------------------------------------------------------------
# Package manifest parsers
# ---------------------------------------------------------------------------

def parse_package_json(project_path: str) -> Optional[dict]:
    pkg_path = Path(project_path) / "package.json"
    if not pkg_path.exists():
        return None
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_pyproject_toml(project_path: str) -> Optional[dict]:
    path = Path(project_path) / "pyproject.toml"
    if not path.exists():
        return None
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                return None
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def read_requirements_txt(project_path: str) -> Optional[List[str]]:
    req_path = Path(project_path) / "requirements.txt"
    if not req_path.exists():
        return None
    try:
        lines = [
            ln.strip() for ln in req_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return lines
    except Exception:
        return None


# ---------------------------------------------------------------------------
# index.html + live server
# ---------------------------------------------------------------------------

def find_index_html(project_path: str) -> Optional[Path]:
    for name in ("index.html", "index.htm", "Index.html"):
        p = Path(project_path) / name
        if p.exists() and p.is_file():
            return p
    return None


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_live_server_state(project_path: str) -> Optional[dict]:
    key = f"live_server::{project_path}"
    state = st.session_state.get(key)
    if state:
        proc = state.get("process")
        if proc and proc.poll() is None:
            return state
        del st.session_state[key]
    return None


def start_live_server(project_path: str) -> int:
    state = get_live_server_state(project_path)
    if state:
        return state["port"]
    port = _find_free_port()
    proc = subprocess.Popen(
        ["python", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=project_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    key = f"live_server::{project_path}"
    st.session_state[key] = {"process": proc, "port": port}
    return port


def stop_live_server(project_path: str) -> None:
    key = f"live_server::{project_path}"
    state = st.session_state.pop(key, None)
    if state:
        proc = state.get("process")
        if proc:
            proc.terminate()


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_project(project_path: str, source_root: str) -> Dict[str, object]:
    project_name = os.path.basename(project_path)
    is_git_repo = os.path.exists(os.path.join(project_path, ".git"))

    total_files = 0
    total_dirs = 0
    logical_size = 0
    allocated_size = 0
    allocated_missing = 0
    has_nested_git = False
    marker_hits = set()
    language_counts: Dict[str, int] = {}
    ext_counts: Dict[str, int] = {}
    one_drive_states: Dict[str, int] = {}
    file_samples: List[Tuple[str, int]] = []
    latest_file_mtime = None
    error_count = 0

    stack = [project_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name == ".git" and entry.is_dir(follow_symlinks=False):
                        has_nested_git = True
                    if entry.is_dir(follow_symlinks=False):
                        try:
                            attrs = entry.stat(follow_symlinks=False).st_file_attributes
                            if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                                continue
                        except Exception:
                            pass
                        total_dirs += 1
                        stack.append(entry.path)
                        continue

                    try:
                        st_info = entry.stat(follow_symlinks=False)
                    except Exception:
                        error_count += 1
                        continue

                    total_files += 1
                    logical_size += int(st_info.st_size)
                    mtime = datetime.fromtimestamp(st_info.st_mtime, tz=timezone.utc).isoformat()
                    if latest_file_mtime is None or mtime > latest_file_mtime:
                        latest_file_mtime = mtime

                    try:
                        attrs = st_info.st_file_attributes
                        state = file_state_from_attrs(attrs)
                        one_drive_states[state] = one_drive_states.get(state, 0) + 1
                    except Exception:
                        pass

                    alloc = get_allocated_size(entry.path)
                    if alloc is None:
                        allocated_missing += 1
                    else:
                        allocated_size += alloc

                    suffix = Path(entry.name).suffix.lower()
                    if suffix:
                        ext_counts[suffix] = ext_counts.get(suffix, 0) + 1
                    language = LANGUAGE_BY_EXTENSION.get(suffix)
                    if language:
                        language_counts[language] = language_counts.get(language, 0) + 1

                    if entry.name in MARKER_FILES:
                        marker_hits.add(entry.name)

                    if len(file_samples) < 300:
                        rel = os.path.relpath(entry.path, project_path)
                        file_samples.append((rel.replace("\\", "/"), int(st_info.st_size)))
        except Exception:
            error_count += 1
            continue

    top_languages = ", ".join([lang for lang, _ in sorted(language_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]])
    top_extensions = ", ".join([ext for ext, _ in sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]])

    remote_url = run_git(project_path, ["remote", "get-url", "origin"]) if is_git_repo else None
    default_branch = run_git(project_path, ["rev-parse", "--abbrev-ref", "HEAD"]) if is_git_repo else None
    last_commit_date = run_git(project_path, ["log", "-1", "--date=iso-strict", "--pretty=%cd"]) if is_git_repo else None
    last_commit_author = run_git(project_path, ["log", "-1", "--pretty=%an"]) if is_git_repo else None

    return {
        "project_name": project_name,
        "project_path": project_path,
        "source_root": source_root,
        "is_git_repo": int(is_git_repo),
        "has_git_tree": int(is_git_repo or has_nested_git),
        "has_remote": int(bool(remote_url)),
        "remote_url": remote_url,
        "remote_owner": parse_remote_owner(remote_url),
        "default_branch": default_branch,
        "last_commit_date": last_commit_date,
        "last_commit_author": last_commit_author,
        "last_file_modified_utc": latest_file_mtime,
        "total_files": total_files,
        "total_dirs": total_dirs,
        "logical_size_bytes": logical_size,
        "allocated_size_bytes": allocated_size if allocated_size > 0 else None,
        "allocated_size_missing_files": allocated_missing,
        "is_empty": int(total_files == 0),
        "top_languages": top_languages,
        "top_extensions": top_extensions,
        "framework_hints": infer_frameworks(sorted(marker_hits)),
        "onedrive_states": json.dumps(one_drive_states, ensure_ascii=True),
        "duplicate_signature": build_signature(file_samples),
        "scan_errors": error_count,
    }


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def initialize_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_name TEXT NOT NULL,
                project_path TEXT NOT NULL,
                source_root TEXT NOT NULL,
                is_git_repo INTEGER NOT NULL,
                has_git_tree INTEGER NOT NULL,
                has_remote INTEGER NOT NULL,
                remote_url TEXT,
                remote_owner TEXT,
                default_branch TEXT,
                last_commit_date TEXT,
                last_commit_author TEXT,
                last_file_modified_utc TEXT,
                total_files INTEGER NOT NULL,
                total_dirs INTEGER NOT NULL,
                logical_size_bytes INTEGER NOT NULL,
                allocated_size_bytes INTEGER,
                allocated_size_missing_files INTEGER NOT NULL,
                is_empty INTEGER NOT NULL,
                top_languages TEXT,
                top_extensions TEXT,
                framework_hints TEXT,
                onedrive_states TEXT,
                duplicate_signature TEXT,
                scan_errors INTEGER NOT NULL,
                scanned_at_utc TEXT NOT NULL
            )
            """
        )


def save_scan(rows: List[Dict[str, object]], db_path: Path) -> None:
    scanned_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM projects")
        for row in rows:
            row["scanned_at_utc"] = scanned_at
            conn.execute(
                """
                INSERT INTO projects (
                    project_name, project_path, source_root, is_git_repo, has_git_tree, has_remote,
                    remote_url, remote_owner, default_branch, last_commit_date, last_commit_author,
                    last_file_modified_utc, total_files, total_dirs, logical_size_bytes,
                    allocated_size_bytes, allocated_size_missing_files, is_empty, top_languages,
                    top_extensions, framework_hints, onedrive_states, duplicate_signature,
                    scan_errors, scanned_at_utc
                ) VALUES (
                    :project_name, :project_path, :source_root, :is_git_repo, :has_git_tree, :has_remote,
                    :remote_url, :remote_owner, :default_branch, :last_commit_date, :last_commit_author,
                    :last_file_modified_utc, :total_files, :total_dirs, :logical_size_bytes,
                    :allocated_size_bytes, :allocated_size_missing_files, :is_empty, :top_languages,
                    :top_extensions, :framework_hints, :onedrive_states, :duplicate_signature,
                    :scan_errors, :scanned_at_utc
                )
                """,
                row,
            )
        conn.commit()


def load_projects(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM projects ORDER BY project_name", conn)


def scan_roots(roots: List[str]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    progress = st.progress(0.0, text="Preparing scan...")
    projects = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for item in sorted(os.listdir(root), key=str.lower):
            full = os.path.join(root, item)
            if os.path.isdir(full):
                projects.append((full, root))
    if not projects:
        progress.empty()
        return rows
    for idx, (project_path, source_root) in enumerate(projects, start=1):
        progress.progress(idx / len(projects), text=f"Scanning {idx}/{len(projects)}: {project_path}")
        rows.append(scan_project(project_path, source_root))
    progress.empty()
    return rows


# ---------------------------------------------------------------------------
# Config persistence (roots survive server restarts)
# ---------------------------------------------------------------------------

def _load_saved_roots() -> List[str]:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            roots = data.get("scan_roots", [])
            if isinstance(roots, list):
                return [str(r) for r in roots]
        except Exception:
            pass
    return []


def _save_roots(roots: List[str]) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps({"scan_roots": roots}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sidebar scan controls
# ---------------------------------------------------------------------------

def render_root_editor() -> Tuple[bool, List[str]]:
    st.header("Scan Controls")

    if "scan_roots_list" not in st.session_state:
        st.session_state["scan_roots_list"] = _load_saved_roots()

    roots = list(st.session_state["scan_roots_list"])

    # Apply any value queued by a Browse pick BEFORE widgets are instantiated.
    # (Streamlit forbids setting a widget's key after the widget is created.)
    pending = st.session_state.pop("_pending_root_update", None)
    if pending is not None:
        p_idx, p_val = pending
        st.session_state[f"scan_root_{p_idx}"] = p_val  # safe: widget not yet created

    st.caption("Paths are saved to disk and persist across restarts.")
    remove_index = None
    for idx in range(len(roots)):
        widget_key = f"scan_root_{idx}"
        cols = st.columns([7, 1, 1])
        roots[idx] = cols[0].text_input(
            f"Root {idx + 1}", value=roots[idx], key=widget_key,
            label_visibility="collapsed",
            placeholder=f"Root {idx + 1} — paste or browse",
        )
        if cols[1].button("📂", key=f"browse_{idx}", use_container_width=True, help="Browse for folder"):
            chosen = pick_folder(roots[idx] if roots[idx].strip() else r"C:\\")
            if chosen:
                roots[idx] = chosen
                st.session_state["scan_roots_list"] = roots
                # Queue the widget value update for the next render cycle
                st.session_state["_pending_root_update"] = (idx, chosen)
                _save_roots(roots)
                st.rerun()

        if cols[2].button("✕", key=f"remove_{idx}", use_container_width=True, help="Remove this root"):
            remove_index = idx

    if remove_index is not None:
        roots.pop(remove_index)
        # Clear widget keys from the removed index onward so they re-render
        # with correct values (keys shift down after removal)
        for i in range(remove_index, len(roots) + 1):
            st.session_state.pop(f"scan_root_{i}", None)
        st.session_state["scan_roots_list"] = roots
        _save_roots(roots)
        st.rerun()

    if st.button("+ Add root", use_container_width=True):
        roots.append("")
        st.session_state["scan_roots_list"] = roots
        _save_roots(roots)
        st.rerun()

    # Persist any manual edits made in the text inputs this render cycle
    st.session_state["scan_roots_list"] = roots
    _save_roots(roots)

    valid = [r.strip() for r in roots if r.strip()]
    if not roots:
        st.info("No roots configured. Add a folder path and run a scan.")
    elif not valid:
        st.warning("Enter at least one valid path.")
    st.caption("Scans immediate child folders under each root.")
    return st.button("Run Full Scan", type="primary", use_container_width=True, disabled=not valid), valid


# ---------------------------------------------------------------------------
# Inventory table
# ---------------------------------------------------------------------------

def apply_inventory_filters(df: pd.DataFrame) -> pd.DataFrame:
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    search_text = c1.text_input("Search name/path", "")
    source_options = sorted(df["source_root"].dropna().unique().tolist())
    selected_sources = c2.multiselect("Roots", source_options, default=source_options)
    git_choice = c3.selectbox("Git", ["All", "With git tree", "Without git tree"])
    remote_choice = c4.selectbox("Remote", ["All", "With remote", "Without remote"])

    d1, d2, d3 = st.columns([1, 1, 2])
    empty_choice = d1.selectbox("Empty", ["All", "Empty only", "Non-empty only"])
    duplicates_choice = d2.selectbox("Duplicates", ["All", "Only duplicate groups", "Unique only"])
    min_files = d3.slider("Min file count", min_value=0, max_value=max(int(df["total_files"].max()), 0), value=0)

    view = df.copy()
    if search_text.strip():
        needle = search_text.strip().lower()
        view = view[
            view["project_name"].str.lower().str.contains(needle, na=False)
            | view["project_path"].str.lower().str.contains(needle, na=False)
        ]
    if selected_sources:
        view = view[view["source_root"].isin(selected_sources)]
    if git_choice == "With git tree":
        view = view[view["has_git_tree"] == 1]
    elif git_choice == "Without git tree":
        view = view[view["has_git_tree"] == 0]
    if remote_choice == "With remote":
        view = view[view["has_remote"] == 1]
    elif remote_choice == "Without remote":
        view = view[view["has_remote"] == 0]
    if empty_choice == "Empty only":
        view = view[view["is_empty"] == 1]
    elif empty_choice == "Non-empty only":
        view = view[view["is_empty"] == 0]
    view = view[view["total_files"] >= min_files]

    signature_counts = view.groupby("duplicate_signature")["project_path"].count().to_dict()
    view["duplicate_group_size"] = view["duplicate_signature"].map(lambda x: signature_counts.get(x, 0))
    if duplicates_choice == "Only duplicate groups":
        view = view[view["duplicate_group_size"] > 1]
    elif duplicates_choice == "Unique only":
        view = view[view["duplicate_group_size"] <= 1]

    name_counts = view.groupby("project_name")["project_path"].count().to_dict()
    view["in_multiple_roots"] = view["project_name"].map(lambda n: 1 if name_counts.get(n, 0) > 1 else 0)
    return view


def render_inventory(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        st.warning("No inventory found yet. Run a scan from the sidebar.")
        return df

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Projects", f"{len(df)}")
    col_b.metric("With Git", f"{int(df['has_git_tree'].sum())}")
    col_c.metric("With Remote", f"{int(df['has_remote'].sum())}")
    col_d.metric("Empty", f"{int(df['is_empty'].sum())}")

    st.subheader("Project Inventory")
    st.caption("Click a row to select a project for the drilldown below.")
    view = apply_inventory_filters(df)
    table = view.copy()
    table["Git"] = table["has_git_tree"].map(lambda v: bool_icon(v, "🌿", "—"))
    table["Remote"] = table["has_remote"].map(lambda v: bool_icon(v, "☁️", "—"))
    table["Remote URL"] = table["remote_url"].map(remote_to_web_url)
    table["Empty"] = table["is_empty"].map(lambda v: bool_icon(v, "📭", "—"))
    table["Both roots"] = table["in_multiple_roots"].map(lambda v: bool_icon(v, "🔁", "—"))
    table["Duplicates"] = table["duplicate_group_size"].map(lambda n: "🧬" if int(n) > 1 else "—")
    table["Logical size"] = table["logical_size_bytes"].map(format_bytes)
    table["On-disk size"] = table["allocated_size_bytes"].map(format_bytes)
    table["Errors"] = table["scan_errors"].map(lambda n: "⚠️" if int(n) > 0 else "—")

    show = table[
        [
            "project_name", "source_root", "Git", "Remote", "remote_owner", "Remote URL",
            "Empty", "Both roots", "Duplicates", "total_files", "total_dirs",
            "Logical size", "On-disk size", "last_commit_date",
            "last_file_modified_utc", "top_languages", "framework_hints", "Errors", "project_path",
        ]
    ].rename(
        columns={
            "project_name": "Project",
            "source_root": "Root",
            "remote_owner": "Owner",
            "total_files": "Files",
            "total_dirs": "Folders",
            "last_commit_date": "Last commit",
            "last_file_modified_utc": "Last file update",
            "top_languages": "Languages",
            "framework_hints": "Frameworks",
            "project_path": "Path",
        }
    )

    event = st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="projects_table",
        column_config={
            "Project": st.column_config.TextColumn(width="medium"),
            "Root": st.column_config.TextColumn(width="medium"),
            "Path": st.column_config.TextColumn(width="large"),
            "Remote URL": st.column_config.LinkColumn(width="large"),
            "Owner": st.column_config.TextColumn(width="small"),
            "Files": st.column_config.NumberColumn(format="%d"),
            "Folders": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(f"Rows shown: {len(show)}")

    if event.selection.rows:
        clicked_path = show.iloc[event.selection.rows[0]]["Path"]
        st.session_state["selected_project_path"] = clicked_path
        st.session_state["active_tab"] = "project"
        st.rerun()

    return view


# ---------------------------------------------------------------------------
# File tree HTML renderer
# ---------------------------------------------------------------------------

def render_file_tree_html(current_path: str, project_path: str, selected_file: str = "") -> str:
    root_name = os.path.basename(project_path)
    try:
        rel = os.path.relpath(current_path, project_path)
        display_path = root_name if rel == "." else f"{root_name}/{rel.replace(chr(92), '/')}"
    except ValueError:
        display_path = root_name

    lines = [
        '<div style="font-family:Consolas,monospace;font-size:12.5px;'
        "background:#1e1e2e;color:#cdd6f4;padding:10px 8px;border-radius:6px;"
        'height:360px;overflow-y:auto;line-height:1.8;user-select:none;">',
        f'<div style="color:#89b4fa;font-weight:bold;margin-bottom:4px;">📂 {display_path}/</div>',
    ]

    try:
        folders: List[str] = []
        files: List[str] = []
        with os.scandir(current_path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.name)
                    else:
                        files.append(entry.name)
                except Exception:
                    pass
        folders.sort(key=str.lower)
        files.sort(key=str.lower)

        for name in folders[:60]:
            lines.append(
                f'<div style="padding-left:14px;color:#89b4fa;">'
                f'📁 {name}/</div>'
            )
        for name in files[:120]:
            icon = get_file_icon(name)
            full = os.path.join(current_path, name)
            is_sel = full == selected_file
            bg = "background:#313244;border-radius:3px;" if is_sel else ""
            color = "#a6e3a1" if is_sel else "#cdd6f4"
            lines.append(
                f'<div style="padding-left:14px;color:{color};{bg}">'
                f'{icon} {name}</div>'
            )
        total = len(folders) + len(files)
        if total > 180:
            lines.append('<div style="color:#6c7086;padding-left:14px;">… more files not shown</div>')
    except Exception as exc:
        lines.append(f'<div style="color:#f38ba8;">Error reading directory: {exc}</div>')

    lines.append("</div>")
    return "".join(lines)


# ---------------------------------------------------------------------------
# File explorer panel
# ---------------------------------------------------------------------------

def list_folder_entries(path: str) -> Tuple[List[os.DirEntry], List[os.DirEntry], List[str]]:
    folders: List[os.DirEntry] = []
    files: List[os.DirEntry] = []
    errors = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry)
                    else:
                        files.append(entry)
                except Exception as exc:
                    errors.append(f"{entry.path}: {exc}")
    except Exception as exc:
        errors.append(str(exc))
    folders.sort(key=lambda d: d.name.lower())
    files.sort(key=lambda d: d.name.lower())
    return folders, files, errors


def render_file_preview(file_path: str) -> None:
    try:
        st_info = os.stat(file_path)
        attrs = getattr(st_info, "st_file_attributes", 0)
        st.caption(f"`{file_path}`  |  {format_bytes(st_info.st_size)}  |  {file_state_from_attrs(attrs)}")
    except Exception as exc:
        st.error(f"Could not stat file: {exc}")
        return

    suffix = Path(file_path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        st.image(file_path, caption=os.path.basename(file_path), use_container_width=True)
        return
    if suffix not in TEXT_EXTENSIONS:
        st.info("Binary or unsupported preview type.")
        return
    if st_info.st_size > 2 * 1024 * 1024:
        st.info("File larger than 2 MB — preview skipped.")
        return

    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        st.error(f"Could not read file: {exc}")
        return

    if suffix == ".md":
        st.markdown(content)
    else:
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "tsx", ".jsx": "jsx", ".json": "json", ".html": "html",
            ".css": "css", ".scss": "scss", ".yaml": "yaml", ".yml": "yaml",
            ".toml": "toml", ".sh": "bash", ".ps1": "powershell",
            ".sql": "sql", ".rs": "rust", ".go": "go", ".java": "java",
            ".cs": "csharp", ".cpp": "cpp", ".c": "c",
        }
        st.code(content, language=lang_map.get(suffix, "text"))


def render_explorer(project_path: str) -> None:
    nav_key = f"nav::{project_path}"
    preview_key = f"preview::{project_path}"

    if nav_key not in st.session_state:
        st.session_state[nav_key] = project_path
    if preview_key not in st.session_state:
        st.session_state[preview_key] = None

    current_path = st.session_state[nav_key]
    selected_file = st.session_state[preview_key]

    # Guard: stay inside project root
    try:
        if not os.path.isdir(current_path) or not os.path.abspath(current_path).startswith(os.path.abspath(project_path)):
            st.session_state[nav_key] = project_path
            current_path = project_path
    except Exception:
        st.session_state[nav_key] = project_path
        current_path = project_path

    # Breadcrumb + Up
    bc1, bc2 = st.columns([1, 9])
    with bc1:
        up_disabled = current_path == project_path
        if st.button("⬆ Up", disabled=up_disabled, use_container_width=True, key=f"up::{project_path}"):
            st.session_state[nav_key] = os.path.dirname(current_path)
            st.session_state[preview_key] = None
            st.rerun()
    with bc2:
        try:
            rel = os.path.relpath(current_path, project_path)
            display = "." if rel == "." else rel.replace("\\", "/")
        except ValueError:
            display = current_path
        st.markdown(
            f'<div style="font-family:Consolas,monospace;font-size:13px;'
            f'background:#1e1e2e;color:#89b4fa;padding:6px 10px;border-radius:4px;">'
            f'📂 {os.path.basename(project_path)} / {display}</div>',
            unsafe_allow_html=True,
        )

    folders, files, errors = list_folder_entries(current_path)
    if errors:
        st.warning("Some entries could not be read.")

    tree_col, preview_col = st.columns([1, 2])

    with tree_col:
        # Visual HTML tree
        st.markdown(
            render_file_tree_html(current_path, project_path, selected_file or ""),
            unsafe_allow_html=True,
        )

        st.markdown("")

        # Folder navigation
        if folders:
            folder_options = [f.path for f in folders[:500]]
            sel_folder = st.selectbox(
                "Navigate into folder",
                folder_options,
                format_func=lambda p: f"📁 {os.path.basename(p)}",
                key=f"folder_select::{current_path}",
            )
            if st.button("Open folder", key=f"open_folder::{current_path}", use_container_width=True):
                st.session_state[nav_key] = sel_folder
                st.session_state[preview_key] = None
                st.rerun()
        else:
            st.caption("No subfolders.")

        st.markdown("---")

        # File selection
        if files:
            file_options = [f.path for f in files[:500]]
            # default to already-selected file if in this dir
            default_idx = 0
            if selected_file and selected_file in file_options:
                default_idx = file_options.index(selected_file)

            sel_file = st.selectbox(
                "Select file",
                file_options,
                index=default_idx,
                format_func=lambda p: f"{get_file_icon(os.path.basename(p))} {os.path.basename(p)}",
                key=f"file_select::{current_path}",
            )
            fc1, fc2 = st.columns(2)
            if fc1.button("Preview", key=f"preview_btn::{current_path}", use_container_width=True):
                st.session_state[preview_key] = sel_file
                st.rerun()
            if fc2.button("Open externally", key=f"open_file::{current_path}", use_container_width=True):
                open_in_explorer(sel_file)
        else:
            st.caption("No files in this folder.")

    with preview_col:
        if selected_file and os.path.isfile(selected_file):
            fname = os.path.basename(selected_file)
            icon = get_file_icon(fname)
            st.markdown(f"**{icon} {fname}**")
            render_file_preview(selected_file)
        else:
            st.markdown(
                '<div style="color:#6c7086;font-size:13px;padding:40px 0;text-align:center;">'
                "Select a file and click Preview to see its contents."
                "</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Package panel
# ---------------------------------------------------------------------------

def _render_index_html_section(project_path: str) -> None:
    index_html = find_index_html(project_path)
    if not index_html:
        return

    st.markdown("---")
    st.markdown("#### 🌐 index.html detected")
    c1, c2, c3 = st.columns([1, 1, 2])

    if c1.button("Open (file://)", key=f"open_html::{project_path}", use_container_width=True):
        webbrowser.open(path_to_file_url(str(index_html)), new=2)

    server_state = get_live_server_state(project_path)
    if server_state:
        port = server_state["port"]
        c2.success(f"Live :{port}")
        if c3.button("Stop server", key=f"stop_srv::{project_path}", use_container_width=True):
            stop_live_server(project_path)
            st.rerun()
        st.markdown(f"[Open http://localhost:{port}](http://localhost:{port})")
    else:
        if c2.button("▶ Start live server", key=f"start_srv::{project_path}", use_container_width=True):
            port = start_live_server(project_path)
            st.success(f"Server started on port {port}. Click the link below.")
            st.rerun()


def render_package_panel(project_path: str) -> None:
    found_any = False

    # --- package.json ---
    pkg = parse_package_json(project_path)
    if pkg:
        found_any = True
        st.markdown("#### 📦 package.json")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Name", pkg.get("name") or "—")
        m2.metric("Version", pkg.get("version") or "—")

        author = pkg.get("author", "")
        if isinstance(author, dict):
            author = author.get("name", "")
        m3.metric("Author", str(author) if author else "—")
        m4.metric("License", str(pkg.get("license") or "—"))

        if pkg.get("description"):
            st.info(pkg["description"])

        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        peer_deps = pkg.get("peerDependencies", {})

        d1, d2, d3 = st.columns(3)
        d1.metric("Dependencies", len(deps))
        d2.metric("Dev Deps", len(dev_deps))
        d3.metric("Peer Deps", len(peer_deps))

        if deps:
            with st.expander(f"Dependencies ({len(deps)})"):
                for name, ver in sorted(deps.items()):
                    st.code(f"{name}: {ver}", language=None)
        if dev_deps:
            with st.expander(f"Dev Dependencies ({len(dev_deps)})"):
                for name, ver in sorted(dev_deps.items()):
                    st.code(f"{name}: {ver}", language=None)
        if peer_deps:
            with st.expander(f"Peer Dependencies ({len(peer_deps)})"):
                for name, ver in sorted(peer_deps.items()):
                    st.code(f"{name}: {ver}", language=None)

        scripts = pkg.get("scripts", {})
        if scripts:
            with st.expander(f"Scripts ({len(scripts)})"):
                for sname, cmd in scripts.items():
                    st.code(f"npm run {sname}  →  {cmd}", language=None)

        engines = pkg.get("engines", {})
        if engines:
            st.caption("Engines: " + "  |  ".join(f"{k}: {v}" for k, v in engines.items()))

    # --- pyproject.toml ---
    pyproject = parse_pyproject_toml(project_path)
    if pyproject:
        found_any = True
        st.markdown("#### 🐍 pyproject.toml")
        meta = pyproject.get("project") or pyproject.get("tool", {}).get("poetry", {})
        if meta:
            m1, m2 = st.columns(2)
            m1.metric("Name", meta.get("name") or "—")
            m2.metric("Version", meta.get("version") or "—")
            if meta.get("description"):
                st.info(meta["description"])

            authors = meta.get("authors", [])
            if authors:
                author_str = ", ".join(
                    a if isinstance(a, str) else a.get("name", str(a)) for a in authors[:3]
                )
                st.caption(f"Authors: {author_str}")

            deps = meta.get("dependencies", {})
            if isinstance(deps, dict):
                if "python" in deps:
                    st.caption(f"Python requires: {deps['python']}")
                    other_deps = {k: v for k, v in deps.items() if k != "python"}
                else:
                    other_deps = deps
                if other_deps:
                    with st.expander(f"Dependencies ({len(other_deps)})"):
                        for dname, ver in sorted(other_deps.items()):
                            st.code(f"{dname}: {ver}", language=None)
            elif isinstance(deps, list) and deps:
                with st.expander(f"Dependencies ({len(deps)})"):
                    for dep in sorted(deps):
                        st.code(str(dep), language=None)

            dev_deps = (
                meta.get("dev-dependencies", {})
                or pyproject.get("tool", {}).get("poetry", {}).get("dev-dependencies", {})
            )
            if dev_deps and isinstance(dev_deps, dict):
                with st.expander(f"Dev Dependencies ({len(dev_deps)})"):
                    for dname, ver in sorted(dev_deps.items()):
                        st.code(f"{dname}: {ver}", language=None)

    # --- requirements.txt ---
    reqs = read_requirements_txt(project_path)
    if reqs is not None:
        found_any = True
        st.markdown("#### 🐍 requirements.txt")
        st.metric("Requirements", len(reqs))
        if reqs:
            with st.expander(f"Packages ({len(reqs)})"):
                for line in reqs:
                    st.code(line, language=None)

    # --- Cargo.toml (basic) ---
    cargo_path = Path(project_path) / "Cargo.toml"
    if cargo_path.exists():
        found_any = True
        st.markdown("#### 🦀 Cargo.toml")
        try:
            content = cargo_path.read_text(encoding="utf-8", errors="replace")
            st.code(content[:1500], language="toml")
        except Exception:
            pass

    # --- go.mod (basic) ---
    go_mod = Path(project_path) / "go.mod"
    if go_mod.exists():
        found_any = True
        st.markdown("#### 🔵 go.mod")
        try:
            st.code(go_mod.read_text(encoding="utf-8", errors="replace")[:1000], language="text")
        except Exception:
            pass

    if not found_any:
        st.info("No package manifest found (package.json, pyproject.toml, requirements.txt, Cargo.toml, go.mod).")

    # Always check for index.html
    _render_index_html_section(project_path)


# ---------------------------------------------------------------------------
# README panel
# ---------------------------------------------------------------------------

def find_root_readme(project_path: str) -> Optional[Path]:
    candidates = ["README.md", "Readme.md", "readme.md", "README.txt", "readme.txt", "README"]
    for name in candidates:
        p = Path(project_path) / name
        if p.exists() and p.is_file():
            return p
    return None


def render_readme_tab(project_path: str) -> None:
    readme = find_root_readme(project_path)
    if not readme:
        st.info("No README found in this project root.")
        return

    st.caption(f"`{readme}`")
    try:
        size = readme.stat().st_size
        if size > 2 * 1024 * 1024:
            st.info("README is larger than 2 MB; preview skipped.")
            return
        content = readme.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        st.error(f"Could not load README: {exc}")
        return

    if readme.suffix.lower() == ".md":
        st.markdown(content)
    else:
        st.code(content)


# ---------------------------------------------------------------------------
# README cards (global tab)
# ---------------------------------------------------------------------------

def render_readme_cards(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No projects in the current view.")
        return

    st.caption(f"Showing {len(df)} projects. Click a card to open the project view.")
    cols_per_row = 3
    projects = df.to_dict("records")

    for i in range(0, len(projects), cols_per_row):
        row_projects = projects[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, project in zip(cols, row_projects):
            with col:
                with st.container(border=True):
                    name = project["project_name"]
                    lang = project.get("top_languages") or ""
                    fw = project.get("framework_hints") or ""
                    is_git = int(project.get("has_git_tree", 0)) == 1
                    has_remote = int(project.get("has_remote", 0)) == 1

                    # Header row
                    badges = []
                    if is_git:
                        badges.append("🌿 git")
                    if has_remote:
                        badges.append("☁️ remote")
                    badge_str = "  ".join(badges)

                    st.markdown(f"**{name}**")
                    if badge_str:
                        st.caption(badge_str)
                    if lang:
                        st.caption(f"🔤 {lang}")
                    if fw:
                        st.caption(f"🔧 {fw}")

                    # README snippet
                    readme = find_root_readme(str(project["project_path"]))
                    if readme:
                        try:
                            content = readme.read_text(encoding="utf-8", errors="replace")
                            # Strip markdown headings for snippet
                            lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
                            snippet = " ".join(lines)[:280].strip()
                            if snippet:
                                st.markdown(
                                    f'<div style="font-size:12px;color:#888;line-height:1.5;">'
                                    f'{snippet}{"…" if len(snippet) == 280 else ""}</div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                st.caption("_README has no body text_")
                        except Exception:
                            st.caption("_Could not read README_")
                    else:
                        st.caption("_No README_")

                    st.markdown("")
                    if st.button("🔍 Open project", key=f"card::{project['project_path']}", use_container_width=True):
                        st.session_state["selected_project_path"] = str(project["project_path"])
                        st.session_state["active_tab"] = "project"
                        st.rerun()


# ---------------------------------------------------------------------------
# Git panel
# ---------------------------------------------------------------------------

def render_git_panel(row: pd.Series) -> None:
    if int(row["has_git_tree"]) != 1:
        st.info("No git repository detected in this project tree.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Branch", row.get("default_branch") or "—")
    m2.metric("Last author", row.get("last_commit_author") or "—")
    m3.metric("Last commit", (row.get("last_commit_date") or "—")[:10])

    remote_web = remote_to_web_url(row.get("remote_url"))
    if remote_web:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"[{remote_web}]({remote_web})")
        if c2.button("Open in browser", key=f"open_remote::{row.get('project_path')}", use_container_width=True):
            webbrowser.open(remote_web, new=2)
    elif row.get("remote_url"):
        st.code(row["remote_url"])
    else:
        st.caption("No remote configured.")

    recent = run_git(str(row["project_path"]), ["log", "-10", "--pretty=%h | %ad | %an | %s", "--date=short"])
    if recent:
        st.markdown("**Recent commits**")
        st.code(recent, language=None)


# ---------------------------------------------------------------------------
# Metadata panel
# ---------------------------------------------------------------------------

def render_metadata_panel(row: pd.Series) -> None:
    cols = st.columns(2)
    with cols[0]:
        st.metric("Total files", row.get("total_files"))
        st.metric("Total folders", row.get("total_dirs"))
        st.metric("Logical size", format_bytes(row.get("logical_size_bytes")))
        st.metric("On-disk size", format_bytes(row.get("allocated_size_bytes")))
    with cols[1]:
        st.metric("Git tree", bool_icon(int(row.get("has_git_tree", 0)), "Yes", "No"))
        st.metric("Remote", bool_icon(int(row.get("has_remote", 0)), "Yes", "No"))
        st.metric("Empty", bool_icon(int(row.get("is_empty", 0)), "Yes", "No"))
        st.metric("Scan errors", int(row.get("scan_errors", 0)))

    st.markdown("---")
    fields = [
        ("Languages", row.get("top_languages") or "—"),
        ("Frameworks", row.get("framework_hints") or "—"),
        ("Extensions", row.get("top_extensions") or "—"),
        ("Last file update", row.get("last_file_modified_utc") or "—"),
        ("OneDrive states", row.get("onedrive_states") or "—"),
        ("Scanned at", row.get("scanned_at_utc") or "—"),
        ("Root", row.get("source_root") or "—"),
        ("Path", row.get("project_path") or "—"),
    ]
    for label, value in fields:
        st.markdown(f"**{label}:** `{value}`")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_NAV_TABLE = "table"
_NAV_PROJECT = "project"
_NAV_READMES = "readmes"


def main() -> None:
    st.set_page_config(page_title="Project Inventory Dashboard", page_icon="🗂️", layout="wide")
    st.title("🗂️ Project Inventory Dashboard")
    st.caption("Read-only developer companion for managing local repos.")

    initialize_db(DB_PATH)

    with st.sidebar:
        scan_now, roots = render_root_editor()

    if scan_now:
        rows = scan_roots(roots)
        save_scan(rows, DB_PATH)
        st.success(f"Scan complete: {len(rows)} projects indexed.")

    df = load_projects(DB_PATH)

    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = _NAV_TABLE

    active = st.session_state["active_tab"]

    # --- Button-based navigation bar (supports programmatic tab switching) ---
    selected_path = st.session_state.get("selected_project_path")
    proj_label = f"🔍 {Path(selected_path).name}" if selected_path else "🔍 Project"

    n1, n2, n3 = st.columns(3)
    if n1.button(
        "📋 Table", use_container_width=True,
        type="primary" if active == _NAV_TABLE else "secondary",
    ):
        st.session_state["active_tab"] = _NAV_TABLE
        st.rerun()
    if n2.button(
        proj_label, use_container_width=True,
        type="primary" if active == _NAV_PROJECT else "secondary",
    ):
        st.session_state["active_tab"] = _NAV_PROJECT
        st.rerun()
    if n3.button(
        "📚 READMEs", use_container_width=True,
        type="primary" if active == _NAV_READMES else "secondary",
    ):
        st.session_state["active_tab"] = _NAV_READMES
        st.rerun()

    st.markdown("---")

    # --- Table view ---
    if active == _NAV_TABLE:
        render_inventory(df)

    # --- Project drilldown ---
    elif active == _NAV_PROJECT:
        if df.empty:
            st.warning("No inventory found. Run a scan first.")
            return

        all_paths = df["project_path"].tolist()
        persisted = st.session_state.get("selected_project_path")
        if persisted not in all_paths:
            persisted = all_paths[0] if all_paths else None
            st.session_state["selected_project_path"] = persisted

        if not persisted:
            st.info("No project selected. Go to the Table and click a row.")
            return

        idx = all_paths.index(persisted)
        chosen_path = st.selectbox(
            "Project",
            all_paths,
            index=idx,
            format_func=lambda p: f"{Path(p).name}   ({p})",
            key="project_selectbox",
        )
        if chosen_path != persisted:
            st.session_state["selected_project_path"] = chosen_path
            st.rerun()

        selected = df[df["project_path"] == chosen_path].iloc[0]

        # Quick action bar
        qa1, qa2, qa3 = st.columns([1, 1, 5])
        if qa1.button("📂 Open in Explorer", use_container_width=True, key="open_proj_explorer"):
            open_in_explorer(str(selected["project_path"]))
        if qa2.button("📂 Open root", use_container_width=True, key="open_root_explorer"):
            open_in_explorer(str(selected["source_root"]))

        # Drilldown sub-tabs (st.tabs is fine here — no programmatic switching needed)
        t_files, t_pkg, t_readme, t_git, t_info = st.tabs([
            "🗂️ Files", "📦 Package", "📖 README", "🌿 Git", "ℹ️ Info"
        ])

        with t_files:
            render_explorer(str(selected["project_path"]))
        with t_pkg:
            render_package_panel(str(selected["project_path"]))
        with t_readme:
            render_readme_tab(str(selected["project_path"]))
        with t_git:
            render_git_panel(selected)
        with t_info:
            render_metadata_panel(selected)

    # --- READMEs cards ---
    elif active == _NAV_READMES:
        st.subheader("README Overview")
        if df.empty:
            st.warning("No inventory found. Run a scan first.")
        else:
            render_readme_cards(df)


if __name__ == "__main__":
    main()
