import ctypes
import hashlib
import json
import os
import socket
import sys
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


DB_PATH = Path(__file__).with_name("depot.db")
CONFIG_PATH = Path(__file__).with_name("depot_config.json")

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

# CDN icon URLs and fallback emojis for well-known ignored folder names.
# CDN icons are used in the detail panel (HTML); emojis in the table column.
IGNORED_FOLDER_CDN_ICONS: Dict[str, Tuple[str, str]] = {
    "node_modules": ("https://cdn.simpleicons.org/npm/CB3837", "npm packages"),
    ".venv":        ("https://cdn.simpleicons.org/python/3776AB", "Python venv"),
    "venv":         ("https://cdn.simpleicons.org/python/3776AB", "Python venv"),
    "__pycache__":  ("https://cdn.simpleicons.org/python/3776AB", "Python cache"),
    ".next":        ("https://cdn.simpleicons.org/nextdotjs/000000", "Next.js build"),
    ".nuxt":        ("https://cdn.simpleicons.org/nuxtdotjs/00DC82", "Nuxt build"),
    "vendor":       ("https://cdn.simpleicons.org/composer/885630", "Composer vendor"),
}
IGNORED_FOLDER_EMOJI: Dict[str, str] = {
    "node_modules": "📦",
    ".venv": "🐍", "venv": "🐍", "__pycache__": "🐍",
    "dist": "📤", "build": "🔨", "vendor": "📦", "target": "🎯",
    ".cache": "💾", "coverage": "📊", ".next": "▲", ".nuxt": "💚",
    ".output": "📤", "out": "📤", ".turbo": "⚡",
}
DEFAULT_IGNORED_FOLDERS = ["node_modules", ".venv", "__pycache__"]

# ---------------------------------------------------------------------------
# User metadata constants
# ---------------------------------------------------------------------------

REPO_META_FILENAME = ".repo-meta.json"

USER_STATUS_OPTIONS = ["", "active", "archived", "completed", "abandoned", "wip", "template"]
# Brand options are NOT hardcoded — they are user-configurable from the dashboard and stored in
# depot_config.json under "custom_brands". This keeps the repo free of personal identifiers.
# Use _get_brand_options() everywhere instead of this constant.
USER_BRAND_OPTIONS     = [""]   # fallback; always prefer _get_brand_options()
USER_TYPE_OPTIONS      = ["", "library", "tool", "game", "website", "api", "experiment"]
USER_OWNERSHIP_OPTIONS = ["", "personal", "client", "employed", "collaborative", "forked"]

USER_STATUS_ICONS: Dict[str, str] = {
    "active":    "🟢",
    "archived":  "🗃️",
    "completed": "✅",
    "abandoned": "💀",
    "wip":       "🚧",
    "template":  "📋",
    "":          "—",
}

USER_META_DEFAULTS: Dict[str, object] = {
    "hidden":       False,
    "status":       "",
    "pinned":       False,
    "tags":         [],
    "category":     "",
    "description":  "",
    "notes":        "",
    # Extended fields
    "display_name": "",
    "brand":        "",
    "type":         "",
    "ownership":    "",
    "portfolio":    [],
    "featured":     False,
    "priority":     50,
    "live_url":     "",
    "demo_url":     "",
}


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


def ignored_folders_badge(ignored_json: str) -> str:
    """Return an emoji-based badge string for display in the inventory table."""
    if not ignored_json:
        return "—"
    try:
        folders = json.loads(ignored_json)
        if not folders:
            return "—"
        return " ".join(IGNORED_FOLDER_EMOJI.get(f, "📁") + " " + f for f in folders)
    except Exception:
        return "—"


def ignored_folders_html(ignored_json: str) -> str:
    """Return HTML with CDN icons for display in the detail panel."""
    if not ignored_json:
        return ""
    try:
        folders = json.loads(ignored_json)
        if not folders:
            return ""
        parts = []
        for f in folders:
            if f in IGNORED_FOLDER_CDN_ICONS:
                url, label = IGNORED_FOLDER_CDN_ICONS[f]
                parts.append(
                    f'<img src="{url}" width="16" height="16" style="vertical-align:middle;margin-right:4px" '
                    f'title="{label}"> <code>{f}</code>'
                )
            else:
                emoji = IGNORED_FOLDER_EMOJI.get(f, "📁")
                parts.append(f'{emoji} <code>{f}</code>')
        return " &nbsp; ".join(parts)
    except Exception:
        return ""


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


def pick_folder(initial_dir: str = "") -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=initial_dir or "")
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

def scan_project(project_path: str, source_root: str, ignored_folders: set = None) -> Dict[str, object]:
    if ignored_folders is None:
        ignored_folders = set()
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
    ignored_found: set = set()

    stack = [project_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name == ".git" and entry.is_dir(follow_symlinks=False):
                        has_nested_git = True
                    if entry.is_dir(follow_symlinks=False):
                        # Skip globally-ignored folder names but record their presence
                        if entry.name in ignored_folders:
                            ignored_found.add(entry.name)
                            continue
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

    result = {
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
        "ignored_folders_found": json.dumps(sorted(ignored_found), ensure_ascii=True),
    }
    result.update(_meta_to_db_fields(read_repo_meta(project_path)))
    return result


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
                ignored_folders_found TEXT,
                scanned_at_utc TEXT NOT NULL,
                user_hidden INTEGER NOT NULL DEFAULT 0,
                user_pinned INTEGER NOT NULL DEFAULT 0,
                user_status TEXT NOT NULL DEFAULT '',
                user_tags TEXT NOT NULL DEFAULT '[]',
                user_category TEXT NOT NULL DEFAULT '',
                user_description TEXT NOT NULL DEFAULT '',
                user_notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Migrations: add columns to existing databases that predate these features
        for _col_def in [
            "ignored_folders_found TEXT",
            "user_hidden INTEGER NOT NULL DEFAULT 0",
            "user_pinned INTEGER NOT NULL DEFAULT 0",
            "user_status TEXT NOT NULL DEFAULT ''",
            "user_tags TEXT NOT NULL DEFAULT '[]'",
            "user_category TEXT NOT NULL DEFAULT ''",
            "user_description TEXT NOT NULL DEFAULT ''",
            "user_notes TEXT NOT NULL DEFAULT ''",
            "user_display_name TEXT NOT NULL DEFAULT ''",
            "user_brand TEXT NOT NULL DEFAULT ''",
            "user_type TEXT NOT NULL DEFAULT ''",
            "user_ownership TEXT NOT NULL DEFAULT ''",
            "user_portfolio TEXT NOT NULL DEFAULT '[]'",
            "user_featured INTEGER NOT NULL DEFAULT 0",
            "user_priority INTEGER NOT NULL DEFAULT 50",
            "user_live_url TEXT NOT NULL DEFAULT ''",
            "user_demo_url TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {_col_def}")
            except Exception:
                pass  # Column already exists


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
                    scan_errors, ignored_folders_found, scanned_at_utc,
                    user_hidden, user_pinned, user_status, user_tags,
                    user_category, user_description, user_notes,
                    user_display_name, user_brand, user_type, user_ownership,
                    user_portfolio, user_featured, user_priority, user_live_url, user_demo_url
                ) VALUES (
                    :project_name, :project_path, :source_root, :is_git_repo, :has_git_tree, :has_remote,
                    :remote_url, :remote_owner, :default_branch, :last_commit_date, :last_commit_author,
                    :last_file_modified_utc, :total_files, :total_dirs, :logical_size_bytes,
                    :allocated_size_bytes, :allocated_size_missing_files, :is_empty, :top_languages,
                    :top_extensions, :framework_hints, :onedrive_states, :duplicate_signature,
                    :scan_errors, :ignored_folders_found, :scanned_at_utc,
                    :user_hidden, :user_pinned, :user_status, :user_tags,
                    :user_category, :user_description, :user_notes,
                    :user_display_name, :user_brand, :user_type, :user_ownership,
                    :user_portfolio, :user_featured, :user_priority, :user_live_url, :user_demo_url
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
    ignored_folders = set(_load_ignored_folders())
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
        rows.append(scan_project(project_path, source_root, ignored_folders))
    progress.empty()
    return rows


# ---------------------------------------------------------------------------
# Config persistence (roots survive server restarts)
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_config(data: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_saved_roots() -> List[str]:
    roots = _load_config().get("scan_roots", [])
    return [str(r) for r in roots] if isinstance(roots, list) else []


def _save_roots(roots: List[str]) -> None:
    data = _load_config()
    data["scan_roots"] = roots
    _save_config(data)


def _load_ignored_folders() -> List[str]:
    cfg = _load_config()
    if "ignored_folders" not in cfg:
        return list(DEFAULT_IGNORED_FOLDERS)
    folders = cfg["ignored_folders"]
    return [str(f) for f in folders] if isinstance(folders, list) else list(DEFAULT_IGNORED_FOLDERS)


def _save_ignored_folders(folders: List[str]) -> None:
    data = _load_config()
    data["ignored_folders"] = folders
    _save_config(data)


def _load_portfolios() -> List[Dict]:
    portfolios = _load_config().get("portfolios", [])
    return portfolios if isinstance(portfolios, list) else []


def _save_portfolios(portfolios: List[Dict]) -> None:
    data = _load_config()
    data["portfolios"] = portfolios
    _save_config(data)


def _load_custom_brands() -> List[str]:
    """Return the user-configured brand names (without the leading empty string)."""
    brands = _load_config().get("custom_brands", [])
    return [str(b).strip() for b in brands if str(b).strip()] if isinstance(brands, list) else []


def _save_custom_brands(brands: List[str]) -> None:
    data = _load_config()
    data["custom_brands"] = [b for b in brands if b.strip()]
    _save_config(data)


def _get_brand_options() -> List[str]:
    """Return the full brand dropdown options: empty sentinel + configured brands."""
    return [""] + _load_custom_brands()


# ---------------------------------------------------------------------------
# Per-project user metadata (.repo-meta.json)
# ---------------------------------------------------------------------------

def read_repo_meta(project_path: str) -> Dict[str, object]:
    """Read .repo-meta.json from a project folder. Returns defaults on any error."""
    path = Path(project_path) / REPO_META_FILENAME
    if not path.exists():
        return dict(USER_META_DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return dict(USER_META_DEFAULTS)
    if not isinstance(raw, dict):
        return dict(USER_META_DEFAULTS)
    result = dict(USER_META_DEFAULTS)
    for key, default in USER_META_DEFAULTS.items():
        val = raw.get(key)
        if val is None:
            continue
        if isinstance(default, bool) and isinstance(val, bool):
            result[key] = val
        elif isinstance(default, int) and not isinstance(default, bool):
            # int fields (e.g. priority); coerce and clamp to 0-100 for priority
            try:
                result[key] = max(0, min(100, int(val))) if key == "priority" else int(val)
            except (TypeError, ValueError):
                pass
        elif isinstance(default, str) and isinstance(val, str):
            result[key] = val
        elif isinstance(default, list) and isinstance(val, list):
            result[key] = [str(t).strip() for t in val if str(t).strip()]
    # Normalise controlled-vocabulary fields
    if result["status"] not in USER_STATUS_OPTIONS:
        result["status"] = ""
    # brand is user-configurable, so accept any non-empty string
    if not isinstance(result["brand"], str):
        result["brand"] = ""
    if result["type"] not in USER_TYPE_OPTIONS:
        result["type"] = ""
    if result["ownership"] not in USER_OWNERSHIP_OPTIONS:
        result["ownership"] = ""
    return result


def write_repo_meta(project_path: str, meta: Dict[str, object]) -> bool:
    """Write .repo-meta.json to the project folder. Returns True on success."""
    path = Path(project_path) / REPO_META_FILENAME
    output = {k: meta[k] for k in USER_META_DEFAULTS if k in meta}
    try:
        path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as exc:
        st.warning(f"Could not save metadata to {path}: {exc}")
        return False


def delete_repo_meta(project_path: str, db_path: Path) -> Tuple[bool, str]:
    """Delete .repo-meta.json (if present) and reset all user_* columns in DB to defaults."""
    path = Path(project_path) / REPO_META_FILENAME
    errors = []
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            errors.append(f"Could not delete file: {exc}")
    try:
        sync_meta_to_db(project_path, dict(USER_META_DEFAULTS), db_path)
    except Exception as exc:
        errors.append(f"Could not reset DB: {exc}")
    if errors:
        return False, " | ".join(errors)
    return True, ""


def sync_meta_from_file(project_path: str, db_path: Path) -> Tuple[bool, str]:
    """Read .repo-meta.json and push its values into the DB. No-op if file missing."""
    path = Path(project_path) / REPO_META_FILENAME
    if not path.exists():
        return False, f"{REPO_META_FILENAME} not found — nothing to sync."
    try:
        meta = read_repo_meta(project_path)
        sync_meta_to_db(project_path, meta, db_path)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _has_meaningful_meta(row: "pd.Series") -> bool:
    """Return True if any user_* DB column holds a non-default value."""
    checks = [
        int(row.get("user_hidden", 0)) != 0,
        int(row.get("user_pinned", 0)) != 0,
        str(row.get("user_status", "")) != "",
        str(row.get("user_tags", "[]")) not in ("[]", ""),
        str(row.get("user_category", "")) != "",
        str(row.get("user_description", "")) != "",
        str(row.get("user_brand", "")) != "",
        str(row.get("user_type", "")) != "",
        str(row.get("user_ownership", "")) != "",
        str(row.get("user_portfolio", "[]")) not in ("[]", ""),
        int(row.get("user_featured", 0)) != 0,
        int(row.get("user_priority", 50)) != 50,
        str(row.get("user_live_url", "")) != "",
        str(row.get("user_demo_url", "")) != "",
        str(row.get("user_display_name", "")) != "",
    ]
    return any(checks)


def _row_to_meta_dict(row: "pd.Series") -> Dict[str, object]:
    """Convert a DB row back to a .repo-meta.json-compatible dict."""
    try:
        tags = json.loads(str(row.get("user_tags") or "[]"))
    except Exception:
        tags = []
    try:
        portfolio = json.loads(str(row.get("user_portfolio") or "[]"))
    except Exception:
        portfolio = []
    return {
        "hidden":       bool(int(row.get("user_hidden", 0))),
        "status":       str(row.get("user_status", "")),
        "pinned":       bool(int(row.get("user_pinned", 0))),
        "tags":         tags,
        "category":     str(row.get("user_category", "")),
        "description":  str(row.get("user_description", "")),
        "notes":        str(row.get("user_notes", "")),
        "display_name": str(row.get("user_display_name", "")),
        "brand":        str(row.get("user_brand", "")),
        "type":         str(row.get("user_type", "")),
        "ownership":    str(row.get("user_ownership", "")),
        "portfolio":    portfolio,
        "featured":     bool(int(row.get("user_featured", 0))),
        "priority":     int(row.get("user_priority", 50)),
        "live_url":     str(row.get("user_live_url", "")),
        "demo_url":     str(row.get("user_demo_url", "")),
    }


def sync_meta_to_db(project_path: str, meta: Dict[str, object], db_path: Path) -> None:
    """Update only the user_* columns for one project in SQLite without a full rescan."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE projects SET
                    user_hidden=?, user_pinned=?, user_status=?,
                    user_tags=?, user_category=?, user_description=?, user_notes=?,
                    user_display_name=?, user_brand=?, user_type=?, user_ownership=?,
                    user_portfolio=?, user_featured=?, user_priority=?,
                    user_live_url=?, user_demo_url=?
                WHERE project_path=?
                """,
                (
                    int(bool(meta.get("hidden"))),
                    int(bool(meta.get("pinned"))),
                    str(meta.get("status") or ""),
                    json.dumps(meta.get("tags") or [], ensure_ascii=False),
                    str(meta.get("category") or ""),
                    str(meta.get("description") or ""),
                    str(meta.get("notes") or ""),
                    str(meta.get("display_name") or ""),
                    str(meta.get("brand") or ""),
                    str(meta.get("type") or ""),
                    str(meta.get("ownership") or ""),
                    json.dumps(meta.get("portfolio") or [], ensure_ascii=False),
                    int(bool(meta.get("featured"))),
                    int(meta.get("priority") if meta.get("priority") is not None else 50),
                    str(meta.get("live_url") or ""),
                    str(meta.get("demo_url") or ""),
                    project_path,
                ),
            )
            conn.commit()
    except Exception as exc:
        st.warning(f"Could not update metadata in database: {exc}")


def _meta_to_db_fields(meta: Dict[str, object]) -> Dict[str, object]:
    """Convert a metadata dict to the flat DB column values used in scan rows."""
    return {
        "user_hidden":       int(bool(meta.get("hidden"))),
        "user_pinned":       int(bool(meta.get("pinned"))),
        "user_status":       str(meta.get("status") or ""),
        "user_tags":         json.dumps(meta.get("tags") or [], ensure_ascii=False),
        "user_category":     str(meta.get("category") or ""),
        "user_description":  str(meta.get("description") or ""),
        "user_notes":        str(meta.get("notes") or ""),
        "user_display_name": str(meta.get("display_name") or ""),
        "user_brand":        str(meta.get("brand") or ""),
        "user_type":         str(meta.get("type") or ""),
        "user_ownership":    str(meta.get("ownership") or ""),
        "user_portfolio":    json.dumps(meta.get("portfolio") or [], ensure_ascii=False),
        "user_featured":     int(bool(meta.get("featured"))),
        "user_priority":     int(meta.get("priority") if meta.get("priority") is not None else 50),
        "user_live_url":     str(meta.get("live_url") or ""),
        "user_demo_url":     str(meta.get("demo_url") or ""),
    }


# ---------------------------------------------------------------------------
# Portfolio generation
# ---------------------------------------------------------------------------

def build_portfolio_entry(row: "pd.Series") -> Dict:
    """Map a DB row (pd.Series) to a depot-portfolio.json item dict."""
    # URL priority chain: user_live_url → user_demo_url is separate, github not yet fetched
    live_url = str(row.get("user_live_url") or "")
    if not live_url:
        live_url = str(row.get("gh_live_url") or "")
    if not live_url:
        live_url = str(row.get("gh_homepage") or "")

    github_url = remote_to_web_url(str(row.get("remote_url") or "")) or ""
    if github_url and "github.com" not in github_url:
        github_url = ""  # only expose GitHub URLs in portfolio

    display_name = str(row.get("user_display_name") or "").strip()
    if not display_name:
        display_name = str(row.get("project_name") or "")

    description = str(row.get("user_description") or "").strip()
    if not description:
        description = str(row.get("gh_description") or "").strip()

    try:
        tags = json.loads(str(row.get("user_tags") or "[]"))
    except Exception:
        tags = []

    try:
        gh_topics = json.loads(str(row.get("gh_topics") or "[]"))
    except Exception:
        gh_topics = []

    last_commit = str(row.get("last_commit_date") or "")
    if last_commit and "T" in last_commit:
        last_commit = last_commit.split("T")[0]

    return {
        "id":              str(row.get("project_name") or ""),
        "display_name":    display_name,
        "description":     description,
        "brand":           str(row.get("user_brand") or ""),
        "type":            str(row.get("user_type") or ""),
        "ownership":       str(row.get("user_ownership") or ""),
        "status":          str(row.get("user_status") or ""),
        "featured":        bool(int(row.get("user_featured") or 0)),
        "priority":        int(row.get("user_priority") or 50),
        "tags":            tags,
        "category":        str(row.get("user_category") or ""),
        "live_url":        live_url,
        "demo_url":        str(row.get("user_demo_url") or ""),
        "github_url":      github_url,
        "gh_stars":        int(row.get("gh_stars") or 0) if row.get("gh_stars") is not None else None,
        "gh_forks":        int(row.get("gh_forks") or 0) if row.get("gh_forks") is not None else None,
        "gh_topics":       gh_topics,
        "top_languages":   str(row.get("top_languages") or ""),
        "framework_hints": str(row.get("framework_hints") or ""),
        "last_commit_date": last_commit,
    }


def generate_portfolio_json(portfolio_id: str, df: "pd.DataFrame") -> Dict:
    """Build the full depot-portfolio.json dict for a given portfolio site."""
    if df.empty:
        items = []
    else:
        # Filter to projects assigned to this portfolio and not hidden
        def _in_portfolio(portfolio_json: str) -> bool:
            try:
                return portfolio_id in json.loads(portfolio_json or "[]")
            except Exception:
                return False

        mask = df["user_portfolio"].apply(_in_portfolio)
        if "user_hidden" in df.columns:
            mask = mask & (df["user_hidden"] != 1)
        filtered = df[mask].copy()

        # Sort: featured first, then by priority desc, then name asc
        if not filtered.empty:
            filtered = filtered.sort_values(
                ["user_featured", "user_priority", "project_name"],
                ascending=[False, False, True],
            ).reset_index(drop=True)

        items = [build_portfolio_entry(row) for _, row in filtered.iterrows()]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator":    "depot",
        "version":      "1",
        "portfolio_id": portfolio_id,
        "items":        items,
    }


def write_portfolio_json(portfolio: Dict, df: "pd.DataFrame") -> Tuple[bool, str]:
    """Write depot-portfolio.json for a portfolio site. Returns (success, path_or_error)."""
    site_path = portfolio.get("path", "").strip()
    output_file = portfolio.get("output_file", "public/depot-portfolio.json").strip()
    if not site_path:
        return False, "Portfolio path is not configured."
    output_path = Path(site_path) / output_file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = generate_portfolio_json(portfolio["id"], df)
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True, str(output_path)
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Sidebar metadata filters
# ---------------------------------------------------------------------------

def render_meta_filters(df: pd.DataFrame) -> Dict[str, object]:
    """Render label/metadata filter widgets in the sidebar and return active filter values."""
    with st.expander("🏷️ Labels & Filters", expanded=False):
        show_hidden = st.checkbox("Show hidden projects", value=False, key="mf_show_hidden")

        selected_statuses = st.multiselect(
            "Status filter",
            options=[s for s in USER_STATUS_OPTIONS if s],
            format_func=lambda s: f"{USER_STATUS_ICONS.get(s, '')} {s}",
            key="mf_statuses",
        )

        # Collect all tags across visible projects
        all_tags: List[str] = []
        if "user_tags" in df.columns:
            for raw in df["user_tags"].dropna():
                try:
                    for t in json.loads(raw):
                        if t and t not in all_tags:
                            all_tags.append(t)
                except Exception:
                    pass
        all_tags.sort()

        selected_tags = st.multiselect("Tag filter", options=all_tags, key="mf_tags")

        selected_brands = st.multiselect(
            "Brand filter",
            options=[b for b in _get_brand_options() if b],
            key="mf_brands",
        )
        selected_types = st.multiselect(
            "Type filter",
            options=[t for t in USER_TYPE_OPTIONS if t],
            key="mf_types",
        )

    return {
        "show_hidden": show_hidden,
        "statuses": selected_statuses,
        "tags": selected_tags,
        "brands": selected_brands,
        "types": selected_types,
    }


# ---------------------------------------------------------------------------
# Sidebar scan controls
# ---------------------------------------------------------------------------

def render_root_editor() -> Tuple[bool, bool, List[str]]:
    # Pre-load roots so we can compute valid before rendering widgets
    if "scan_roots_list" not in st.session_state:
        st.session_state["scan_roots_list"] = _load_saved_roots()
    roots_precheck = list(st.session_state["scan_roots_list"])
    valid_precheck = [r.strip() for r in roots_precheck if r.strip()]

    # ── Primary action — always visible at the top ──────────────────────────
    scan_now = st.button(
        "Run Full Scan",
        type="primary",
        use_container_width=True,
        disabled=not valid_precheck,
        help="Scan all configured roots and update the inventory",
    )

    if not valid_precheck:
        st.caption("Add a scan root below to enable scanning.")

    # ── Scan Roots — expanded by default ────────────────────────────────────
    with st.expander("Scan Roots", expanded=True):
        roots = list(st.session_state["scan_roots_list"])

        # Apply any value queued by a Browse pick BEFORE widgets are instantiated.
        pending = st.session_state.pop("_pending_root_update", None)
        if pending is not None:
            p_idx, p_val = pending
            st.session_state[f"scan_root_{p_idx}"] = p_val

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
            if cols[1].button("📂", key=f"browse_{idx}", use_container_width=True, help="Browse"):
                chosen = pick_folder(roots[idx] if roots[idx].strip() else r"C:\\")
                if chosen:
                    roots[idx] = chosen
                    st.session_state["scan_roots_list"] = roots
                    st.session_state["_pending_root_update"] = (idx, chosen)
                    _save_roots(roots)
                    st.rerun()
            if cols[2].button("✕", key=f"remove_{idx}", use_container_width=True, help="Remove"):
                remove_index = idx

        if remove_index is not None:
            roots.pop(remove_index)
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

        st.session_state["scan_roots_list"] = roots
        _save_roots(roots)

    valid = [r.strip() for r in roots if r.strip()]

    # ── Crawl & Auto-tag (optional) ─────────────────────────────────────────
    crawl_script = Path(__file__).with_name("crawl_and_tag.py")
    crawl_clicked = False
    if crawl_script.exists():
        crawl_clicked = st.button(
            "Crawl & Auto-tag",
            use_container_width=True,
            disabled=not valid,
            help="Classify projects and write .repo-meta.json (never overwrites manual tags)",
        )

    # ── Ignored Folders — collapsed by default ──────────────────────────────
    with st.expander("Ignored Folders", expanded=False):
        st.caption("Folder names skipped during counting. Their presence is still shown as badges.")

        if "ignored_folders_list" not in st.session_state:
            st.session_state["ignored_folders_list"] = _load_ignored_folders()
        ignored = list(st.session_state["ignored_folders_list"])

        remove_ignored_idx = None
        for i, fname in enumerate(ignored):
            icon = IGNORED_FOLDER_EMOJI.get(fname, "📁")
            cols = st.columns([6, 1])
            cols[0].markdown(f"{icon} `{fname}`")
            if cols[1].button("✕", key=f"rm_ignored_{i}", help="Remove", use_container_width=True):
                remove_ignored_idx = i

        if remove_ignored_idx is not None:
            ignored.pop(remove_ignored_idx)
            st.session_state["ignored_folders_list"] = ignored
            _save_ignored_folders(ignored)
            st.rerun()

        new_name = st.text_input(
            "Add ignored folder", key="new_ignored_folder_input",
            placeholder="e.g. node_modules, dist, .cache",
            label_visibility="collapsed",
        )
        if st.button("+ Add ignored folder", use_container_width=True):
            name = new_name.strip()
            if name and name not in ignored:
                ignored.append(name)
                st.session_state["ignored_folders_list"] = ignored
                _save_ignored_folders(ignored)
                st.rerun()

    # ── Brand Labels — collapsed by default ─────────────────────────────────
    with st.expander("Brand Labels", expanded=False):
        st.caption("Custom brand names used in project labels and portfolio sync.")
        custom_brands = _load_custom_brands()

        remove_brand_idx = None
        for i, brand in enumerate(custom_brands):
            bc1, bc2 = st.columns([5, 1])
            bc1.markdown(f"`{brand}`")
            if bc2.button("✕", key=f"rm_brand_{i}", help="Remove", use_container_width=True):
                remove_brand_idx = i

        if remove_brand_idx is not None:
            custom_brands.pop(remove_brand_idx)
            _save_custom_brands(custom_brands)
            st.rerun()

        new_brand_input = st.text_input(
            "Add brand", key="new_brand_input",
            placeholder="e.g. acme, myco, personal",
            label_visibility="collapsed",
        )
        if st.button("+ Add brand", use_container_width=True):
            nb = new_brand_input.strip().lower()
            if nb and nb not in custom_brands:
                custom_brands.append(nb)
                _save_custom_brands(custom_brands)
                st.rerun()

    return scan_now, crawl_clicked, valid


# ---------------------------------------------------------------------------
# Inventory table
# ---------------------------------------------------------------------------

def apply_inventory_filters(df: pd.DataFrame, meta_filters: Optional[Dict[str, object]] = None) -> pd.DataFrame:
    # Primary filters — always visible
    c1, c2 = st.columns([3, 2])
    search_text = c1.text_input("Search", "", placeholder="project name or path…", label_visibility="collapsed")
    source_options = sorted(df["source_root"].dropna().unique().tolist())
    selected_sources = c2.multiselect("Roots", source_options, default=source_options, label_visibility="collapsed",
                                      placeholder="All roots")

    # Advanced filters — collapsed by default
    with st.expander("Advanced filters", expanded=False):
        d1, d2, d3, d4 = st.columns([1, 1, 1, 2])
        git_choice = d1.selectbox("Git", ["All", "With git tree", "Without git tree"])
        remote_choice = d2.selectbox("Remote", ["All", "With remote", "Without remote"])
        empty_choice = d3.selectbox("Empty", ["All", "Empty only", "Non-empty only"])
        duplicates_choice = d4.selectbox("Duplicates", ["All", "Only duplicate groups", "Unique only"])
        min_files = st.slider("Min file count", min_value=0, max_value=max(int(df["total_files"].max()), 0), value=0)

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

    if meta_filters:
        if not meta_filters.get("show_hidden", False):
            if "user_hidden" in view.columns:
                view = view[view["user_hidden"] != 1]
        selected_statuses = meta_filters.get("statuses") or []
        if selected_statuses and "user_status" in view.columns:
            view = view[view["user_status"].isin(selected_statuses)]
        selected_tags = meta_filters.get("tags") or []
        if selected_tags and "user_tags" in view.columns:
            def _has_any_tag(tags_json: str) -> bool:
                try:
                    return any(t in selected_tags for t in json.loads(tags_json or "[]"))
                except Exception:
                    return False
            view = view[view["user_tags"].apply(_has_any_tag)]
        selected_brands = meta_filters.get("brands") or []
        if selected_brands and "user_brand" in view.columns:
            view = view[view["user_brand"].isin(selected_brands)]
        selected_types = meta_filters.get("types") or []
        if selected_types and "user_type" in view.columns:
            view = view[view["user_type"].isin(selected_types)]

    return view


def render_inventory(df: pd.DataFrame, meta_filters: Optional[Dict[str, object]] = None) -> pd.DataFrame:
    if df.empty:
        st.warning("No inventory found yet. Run a scan from the sidebar.")
        return df

    # Compact inline stats — one line, no wasted vertical space
    git_n    = int(df["has_git_tree"].sum())
    remote_n = int(df["has_remote"].sum())
    empty_n  = int(df["is_empty"].sum())
    hidden_n = int((df["user_hidden"] == 1).sum()) if "user_hidden" in df.columns else 0
    stats_parts = [
        f"**{len(df)}** projects",
        f"🌿 {git_n} git",
        f"☁️ {remote_n} remote",
        f"📭 {empty_n} empty",
    ]
    if hidden_n and not (meta_filters or {}).get("show_hidden", False):
        stats_parts.append(f"🙈 {hidden_n} hidden")
    st.caption("  ·  ".join(stats_parts) + "   —   click any row to open project")

    view = apply_inventory_filters(df, meta_filters)

    # Pinned projects float to top
    if "user_pinned" in view.columns:
        view = view.sort_values(["user_pinned", "project_name"], ascending=[False, True]).reset_index(drop=True)

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
    if "ignored_folders_found" in table.columns:
        table["Ignored"] = table["ignored_folders_found"].map(ignored_folders_badge)
    else:
        table["Ignored"] = "—"
    if "user_status" in table.columns:
        table["Status"] = table["user_status"].map(
            lambda s: (USER_STATUS_ICONS.get(s or "", "—") + (" " + s if s else "")).strip()
        )
    else:
        table["Status"] = "—"
    if "user_tags" in table.columns:
        def _fmt_tags(tags_json: str) -> str:
            try:
                tags = json.loads(tags_json or "[]")
                return ", ".join(tags) if tags else "—"
            except Exception:
                return "—"
        table["Tags"] = table["user_tags"].apply(_fmt_tags)
    else:
        table["Tags"] = "—"
    if "user_pinned" in table.columns:
        table["Pin"] = table["user_pinned"].map(lambda v: "📌" if int(v) == 1 else "—")
    else:
        table["Pin"] = "—"

    show = table[
        [
            "Pin", "Status", "project_name", "Tags", "source_root", "Git", "Remote", "remote_owner", "Remote URL",
            "Empty", "Both roots", "Duplicates", "total_files", "total_dirs",
            "Logical size", "On-disk size", "last_commit_date",
            "last_file_modified_utc", "top_languages", "framework_hints", "Ignored", "Errors", "project_path",
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
            "Pin": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
            "Tags": st.column_config.TextColumn(width="medium"),
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

    if "user_hidden" in df.columns:
        df = df[df["user_hidden"] != 1]

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
    ignored_html = ignored_folders_html(row.get("ignored_folders_found") or "")
    if ignored_html:
        st.markdown("**Ignored folders detected:**")
        st.markdown(ignored_html, unsafe_allow_html=True)
        st.markdown("")

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
# User metadata editor
# ---------------------------------------------------------------------------

def render_user_meta_editor(project_path: str, db_path: Path) -> None:
    """Render the Labels & Notes expander for per-project user metadata."""
    with st.expander("🏷️ Labels & Notes", expanded=False):
        meta = read_repo_meta(project_path)
        st.caption(f"Stored in `{REPO_META_FILENAME}` inside the project folder. Survives rescans.")

        col1, col2 = st.columns(2)
        with col1:
            new_hidden = st.checkbox(
                "Hidden (exclude from main table)",
                value=bool(meta["hidden"]),
                key=f"meta_hidden::{project_path}",
            )
            new_pinned = st.checkbox(
                "Pinned (show first in table)",
                value=bool(meta["pinned"]),
                key=f"meta_pinned::{project_path}",
            )
        with col2:
            status_idx = USER_STATUS_OPTIONS.index(str(meta["status"])) if meta["status"] in USER_STATUS_OPTIONS else 0
            new_status = st.selectbox(
                "Status",
                options=USER_STATUS_OPTIONS,
                index=status_idx,
                key=f"meta_status::{project_path}",
                format_func=lambda s: (f"{USER_STATUS_ICONS.get(s, '')} {s}").strip() if s else "— (none)",
            )
            new_category = st.text_input(
                "Category",
                value=str(meta["category"]),
                key=f"meta_category::{project_path}",
                placeholder="e.g. Work, Learning, Games",
            )

        tags_raw = st.text_input(
            "Tags (comma-separated)",
            value=", ".join(meta["tags"]) if meta["tags"] else "",  # type: ignore[arg-type]
            key=f"meta_tags::{project_path}",
            placeholder="e.g. frontend, work, learning",
        )

        new_description = st.text_area(
            "Description",
            value=str(meta["description"]),
            key=f"meta_description::{project_path}",
            height=80,
            placeholder="Short description of this project",
        )
        new_notes = st.text_area(
            "Private notes",
            value=str(meta["notes"]),
            key=f"meta_notes::{project_path}",
            height=60,
            placeholder="Internal notes (not shown in table)",
        )

        st.markdown("**Identity & Publishing**")
        id1, id2, id3, id4 = st.columns(4)
        new_display_name = id1.text_input(
            "Display name",
            value=str(meta["display_name"]),
            key=f"meta_display_name::{project_path}",
            placeholder="Pretty name for portfolios",
        )
        brand_opts = _get_brand_options()
        brand_idx = brand_opts.index(str(meta["brand"])) if meta["brand"] in brand_opts else 0
        new_brand = id2.selectbox(
            "Brand",
            options=brand_opts,
            index=brand_idx,
            key=f"meta_brand::{project_path}",
            format_func=lambda s: s if s else "— (none)",
        )
        type_idx = USER_TYPE_OPTIONS.index(str(meta["type"])) if meta["type"] in USER_TYPE_OPTIONS else 0
        new_type = id3.selectbox(
            "Type",
            options=USER_TYPE_OPTIONS,
            index=type_idx,
            key=f"meta_type::{project_path}",
            format_func=lambda s: s if s else "— (none)",
        )
        own_idx = USER_OWNERSHIP_OPTIONS.index(str(meta["ownership"])) if meta["ownership"] in USER_OWNERSHIP_OPTIONS else 0
        new_ownership = id4.selectbox(
            "Ownership",
            options=USER_OWNERSHIP_OPTIONS,
            index=own_idx,
            key=f"meta_ownership::{project_path}",
            format_func=lambda s: s if s else "— (none)",
        )

        url1, url2 = st.columns(2)
        new_live_url = url1.text_input(
            "Live URL",
            value=str(meta["live_url"]),
            key=f"meta_live_url::{project_path}",
            placeholder="https://your-deployment.vercel.app",
        )
        new_demo_url = url2.text_input(
            "Demo URL",
            value=str(meta["demo_url"]),
            key=f"meta_demo_url::{project_path}",
            placeholder="https://demo.example.com",
        )

        fp1, fp2 = st.columns([1, 2])
        new_featured = fp1.checkbox(
            "Featured",
            value=bool(meta["featured"]),
            key=f"meta_featured::{project_path}",
            help="Highlighted in portfolio output",
        )
        new_priority = fp2.slider(
            "Priority (0–100)",
            min_value=0, max_value=100,
            value=int(meta["priority"]),  # type: ignore[arg-type]
            key=f"meta_priority::{project_path}",
            help="Higher = shown first in portfolio",
        )

        portfolio_options = [p["id"] for p in _load_portfolios()]
        current_portfolio = meta["portfolio"] if isinstance(meta["portfolio"], list) else []
        new_portfolio = st.multiselect(
            "Appears in portfolios",
            options=portfolio_options,
            default=[p for p in current_portfolio if p in portfolio_options],
            key=f"meta_portfolio::{project_path}",
            help="Configure portfolio sites on the Portfolios page" if not portfolio_options else None,
        )
        if not portfolio_options:
            st.caption("No portfolios configured yet — add them on the 📤 Portfolios page.")

        if st.button("💾 Save labels", key=f"meta_save::{project_path}", type="primary", use_container_width=True):
            new_tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            updated: Dict[str, object] = {
                "hidden":       new_hidden,
                "status":       new_status,
                "pinned":       new_pinned,
                "tags":         new_tags,
                "category":     new_category.strip(),
                "description":  new_description.strip(),
                "notes":        new_notes.strip(),
                "display_name": new_display_name.strip(),
                "brand":        new_brand,
                "type":         new_type,
                "ownership":    new_ownership,
                "live_url":     new_live_url.strip(),
                "demo_url":     new_demo_url.strip(),
                "featured":     new_featured,
                "priority":     new_priority,
                "portfolio":    new_portfolio,
            }
            ok = write_repo_meta(project_path, updated)
            if ok:
                sync_meta_to_db(project_path, updated, db_path)
                st.success("Saved.")
                st.rerun()


# ---------------------------------------------------------------------------
# Portfolios page
# ---------------------------------------------------------------------------

def render_portfolios_page(df: "pd.DataFrame") -> None:
    st.header("📤 Portfolios")
    st.caption(
        "Configure portfolio sites, assign projects, and sync the generated `depot-portfolio.json` "
        "into each site's `public/` folder. Each site fetches this file at runtime."
    )

    # ── Section 1: Portfolio Registry ──────────────────────────────────────
    with st.expander("Portfolio Sites", expanded=True):
        portfolios = _load_portfolios()

        remove_idx = None
        for idx, p in enumerate(portfolios):
            c1, c2, c3, c4 = st.columns([2, 3, 2, 1])
            p["id"] = c1.text_input(
                "ID", value=p.get("id", ""), key=f"port_id_{idx}",
                label_visibility="collapsed", placeholder="id (slug)"
            )
            p["name"] = c2.text_input(
                "Name", value=p.get("name", ""), key=f"port_name_{idx}",
                label_visibility="collapsed", placeholder="Display name"
            )
            p["path"] = c3.text_input(
                "Path", value=p.get("path", ""), key=f"port_path_{idx}",
                label_visibility="collapsed", placeholder="D:/Code/my-site"
            )
            if c4.button("✕", key=f"port_remove_{idx}", use_container_width=True, help="Remove"):
                remove_idx = idx
            # Output file (secondary row)
            p["output_file"] = st.text_input(
                "Output file (relative to site path)",
                value=p.get("output_file", "public/depot-portfolio.json"),
                key=f"port_output_{idx}",
                placeholder="public/depot-portfolio.json",
            )
            st.markdown("---")

        if remove_idx is not None:
            portfolios.pop(remove_idx)
            _save_portfolios(portfolios)
            st.rerun()

        if portfolios:
            # Persist any edits made in text inputs this cycle
            _save_portfolios(portfolios)

        if st.button("+ Add portfolio site", use_container_width=True):
            portfolios.append({"id": "", "name": "", "path": "", "output_file": "public/depot-portfolio.json"})
            _save_portfolios(portfolios)
            st.rerun()

    portfolios = _load_portfolios()  # reload after possible edits

    if not portfolios:
        st.info("No portfolio sites configured yet. Add one above.")
        return

    # ── Section 2: Assignment Overview ─────────────────────────────────────
    st.subheader("Assignment Overview")
    st.caption("Which projects are assigned to each portfolio. Edit assignments in the Project → Labels editor.")

    if df.empty:
        st.info("No projects scanned yet. Run a scan first.")
    else:
        port_ids = [p["id"] for p in portfolios if p.get("id")]

        overview_rows = []
        view = df[df.get("user_hidden", pd.Series(dtype=int)) != 1] if "user_hidden" in df.columns else df
        for _, row in view.iterrows():
            try:
                assigned = json.loads(str(row.get("user_portfolio") or "[]"))
            except Exception:
                assigned = []
            entry: Dict[str, object] = {
                "Project": str(row.get("user_display_name") or row.get("project_name") or ""),
                "Brand": str(row.get("user_brand") or "—"),
                "Type": str(row.get("user_type") or "—"),
                "Status": str(row.get("user_status") or "—"),
                "Featured": "⭐" if int(row.get("user_featured") or 0) else "",
                "Priority": int(row.get("user_priority") or 50),
            }
            for pid in port_ids:
                entry[pid] = "✓" if pid in assigned else ""
            overview_rows.append(entry)

        if overview_rows:
            overview_df = pd.DataFrame(overview_rows)
            st.dataframe(overview_df, use_container_width=True, hide_index=True)
        else:
            st.info("No visible projects found.")

    # ── Section 3: Sync Controls ────────────────────────────────────────────
    st.subheader("Sync Controls")

    sync_all = st.button("🔄 Sync All Portfolios", type="primary")

    for p in portfolios:
        if not p.get("id"):
            continue
        pid = p["id"]
        site_exists = Path(p.get("path", "")).exists() if p.get("path") else False

        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown(f"**{p.get('name') or pid}**  \n`{p.get('path', '—')}`")

            # Count assigned projects
            if not df.empty and "user_portfolio" in df.columns:
                def _cnt(pj: str) -> bool:
                    try:
                        return pid in json.loads(pj or "[]")
                    except Exception:
                        return False
                count = int(df["user_portfolio"].apply(_cnt).sum())
                hidden_count = int((df["user_hidden"] == 1).sum()) if "user_hidden" in df.columns else 0
                h2.metric("Assigned", count)
            else:
                count = 0

            if not site_exists:
                st.warning(f"Path not found: `{p.get('path')}`")

            with st.expander("Preview JSON output"):
                preview_data = generate_portfolio_json(pid, df if not df.empty else pd.DataFrame())
                st.json(preview_data)

            sync_btn = st.button(
                f"Sync → {p.get('output_file', 'public/depot-portfolio.json')}",
                key=f"sync_{pid}",
                disabled=not site_exists or df.empty,
            )

            if sync_btn or (sync_all and site_exists and not df.empty):
                ok, result = write_portfolio_json(p, df)
                if ok:
                    st.success(f"Written to `{result}` ({count} projects)")
                else:
                    st.error(f"Sync failed: {result}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_NAV_TABLE = "table"
_NAV_PROJECT = "project"
_NAV_READMES = "readmes"
_NAV_HIDDEN = "hidden"
_NAV_PORTFOLIOS = "portfolios"


def main() -> None:
    st.set_page_config(page_title="Depot", page_icon="🗂️", layout="wide")
    st.title("🗂️ Depot")
    st.caption("Your local project depot.")

    initialize_db(DB_PATH)

    with st.sidebar:
        scan_now, crawl_clicked, roots = render_root_editor()

    df = load_projects(DB_PATH)

    with st.sidebar:
        meta_filters = render_meta_filters(df)

    if scan_now:
        rows = scan_roots(roots)
        save_scan(rows, DB_PATH)
        st.success(f"Scan complete: {len(rows)} projects indexed.")
        df = load_projects(DB_PATH)

    # Crawl & Auto-tag handler (runs crawl_and_tag.py --sync-db)
    crawl_script = Path(__file__).with_name("crawl_and_tag.py")
    if crawl_script.exists() and crawl_clicked:
        with st.spinner("Crawling and tagging projects..."):
            try:
                proc = subprocess.run(
                    [sys.executable, str(crawl_script), "--sync-db"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                out = proc.stdout + "\n" + proc.stderr if proc.stdout or proc.stderr else "(no output)"
                if proc.returncode == 0:
                    st.success("Crawl & Auto-tag complete.")
                    st.code(out, language="text")
                    df = load_projects(DB_PATH)
                else:
                    st.error("Crawl & Auto-tag failed.")
                    st.code(out, language="text")
            except subprocess.TimeoutExpired:
                st.error("Crawl & Auto-tag timed out (5 min).")
            except Exception as exc:
                st.error(f"Crawl & Auto-tag error: {exc}")

    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = _NAV_TABLE

    active = st.session_state["active_tab"]

    # --- Button-based navigation bar (supports programmatic tab switching) ---
    selected_path = st.session_state.get("selected_project_path")
    proj_label = f"🔍 {Path(selected_path).name}" if selected_path else "🔍 Project"

    n1, n2, n3, n4, n5 = st.columns(5)
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
    if n4.button(
        "🙈 Hidden", use_container_width=True,
        type="primary" if active == _NAV_HIDDEN else "secondary",
    ):
        st.session_state["active_tab"] = _NAV_HIDDEN
        st.rerun()
    if n5.button(
        "📤 Portfolios", use_container_width=True,
        type="primary" if active == _NAV_PORTFOLIOS else "secondary",
    ):
        st.session_state["active_tab"] = _NAV_PORTFOLIOS
        st.rerun()

    st.markdown("---")

    # --- Table view ---
    if active == _NAV_TABLE:
        render_inventory(df, meta_filters)

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
        project_path = str(selected["project_path"])

        # Quick action bar
        qa1, qa2 = st.columns([1, 1])
        if qa1.button("📂 Open folder", use_container_width=True, key="open_proj_explorer"):
            open_in_explorer(project_path)
        if qa2.button("📂 Open root", use_container_width=True, key="open_root_explorer"):
            open_in_explorer(str(selected["source_root"]))

        # ── Metadata status bar — always visible ─────────────────────────────
        meta_file = Path(project_path) / REPO_META_FILENAME
        file_exists = meta_file.exists()
        db_has_data = _has_meaningful_meta(selected)
        confirm_reset_key = f"confirm_reset::{project_path}"

        with st.container(border=True):
            if not file_exists and db_has_data:
                # ⚠️ STALE: file gone, DB still has labels → will be wiped on next rescan
                st.warning(
                    f"**`.repo-meta.json` was deleted** but this project still has labels in the "
                    f"database. They will be wiped on the next full rescan.",
                    icon="⚠️",
                )
                sb1, sb2, sb3 = st.columns([2, 2, 3])
                if sb1.button("Recreate file from DB", key="recreate_meta_file", use_container_width=True,
                              help="Write current DB labels back to .repo-meta.json"):
                    ok = write_repo_meta(project_path, _row_to_meta_dict(selected))
                    if ok:
                        st.success(f"`.repo-meta.json` recreated.")
                        st.rerun()
                if sb2.button("Reset DB to defaults", key="reset_meta_stale", use_container_width=True,
                              type="primary", help="Clear stale labels from the database"):
                    st.session_state[confirm_reset_key] = True

            elif file_exists and db_has_data:
                # ✅ NORMAL: file and DB both have labels
                sb1, sb2, sb3 = st.columns([3, 1, 1])
                label_count = sum([
                    bool(str(selected.get("user_description", ""))),
                    bool(str(selected.get("user_brand", ""))),
                    str(selected.get("user_portfolio", "[]")) not in ("[]", ""),
                    str(selected.get("user_status", "")) != "",
                ])
                sb1.caption(f"🏷️  `.repo-meta.json` present — {label_count} key fields set")
                if sb2.button("🔄 Reload", key="reload_meta_from_file", use_container_width=True,
                              help="Re-read .repo-meta.json and update the database (use after manual file edits)"):
                    ok, msg = sync_meta_from_file(project_path, DB_PATH)
                    if ok:
                        st.success("Database updated from file.")
                        st.rerun()
                    else:
                        st.error(msg)
                if sb3.button("🗑️ Reset", key="reset_meta_labeled", use_container_width=True,
                              help="Delete .repo-meta.json and clear all labels from the database"):
                    st.session_state[confirm_reset_key] = True

            elif file_exists and not db_has_data:
                # File exists but DB is empty — can happen if file was added manually
                sb1, sb2 = st.columns([3, 1])
                sb1.caption("🏷️  `.repo-meta.json` found — not yet synced to database")
                if sb2.button("🔄 Sync to DB", key="sync_meta_to_db_btn", use_container_width=True):
                    ok, msg = sync_meta_from_file(project_path, DB_PATH)
                    if ok:
                        st.success("Synced.")
                        st.rerun()
                    else:
                        st.error(msg)

            else:
                # Clean: no file, no DB data
                st.caption("No labels yet — expand **Labels & Notes** below to add them.")

            # ── Reset confirmation — inline, prominent ────────────────────────
            if st.session_state.get(confirm_reset_key):
                try:
                    affected = json.loads(str(selected.get("user_portfolio") or "[]"))
                except Exception:
                    affected = []
                port_note = (
                    f" Project is assigned to **{len(affected)} portfolio(s)** — "
                    f"those will be re-synced automatically."
                ) if affected else ""

                st.error(
                    f"**This will permanently delete `.repo-meta.json`** (if it exists) and clear "
                    f"all labels from the database.{port_note}  \nThis cannot be undone.",
                )
                rc1, rc2, rc3 = st.columns([2, 2, 4])
                if rc1.button("Yes, reset everything", key=f"reset_confirm_yes::{project_path}",
                              type="primary", use_container_width=True):
                    ok, err = delete_repo_meta(project_path, DB_PATH)
                    if ok:
                        resync_msg = ""
                        if affected:
                            fresh_df = load_projects(DB_PATH)
                            portfolios_cfg = _load_portfolios()
                            resynced = []
                            for pid in affected:
                                port = next((p for p in portfolios_cfg if p.get("id") == pid), None)
                                if port and Path(port.get("path", "")).exists():
                                    w_ok, _ = write_portfolio_json(port, fresh_df)
                                    if w_ok:
                                        resynced.append(pid)
                            if resynced:
                                resync_msg = f"  Resynced portfolios: {', '.join(resynced)}."
                        st.success(f"Reset complete.{resync_msg}")
                    else:
                        st.error(f"Reset failed: {err}")
                    st.session_state.pop(confirm_reset_key, None)
                    st.rerun()
                if rc2.button("Cancel", key=f"reset_confirm_no::{project_path}", use_container_width=True):
                    st.session_state.pop(confirm_reset_key, None)
                    st.rerun()

        # ── Labels editor (expander, for editing fields) ─────────────────────
        render_user_meta_editor(project_path, DB_PATH)

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

    # --- Hidden / archived view ---
    elif active == _NAV_HIDDEN:
        st.subheader("🙈 Hidden & Archived Projects")
        if df.empty:
            st.warning("No inventory found. Run a scan first.")
        else:
            hidden_mask = (df.get("user_hidden", pd.Series(dtype=int)) == 1) if "user_hidden" in df.columns else pd.Series([False] * len(df))
            archived_mask = (df.get("user_status", pd.Series(dtype=str)) == "archived") if "user_status" in df.columns else pd.Series([False] * len(df))
            combined = df[hidden_mask | archived_mask].drop_duplicates(subset=["project_path"])
            if combined.empty:
                st.info("No hidden or archived projects. Mark projects as hidden or archived using the 🏷️ Labels & Notes editor in the Project view.")
            else:
                render_inventory(combined, meta_filters={"show_hidden": True, "statuses": [], "tags": [], "brands": [], "types": []})

    # --- Portfolios ---
    elif active == _NAV_PORTFOLIOS:
        render_portfolios_page(df)


if __name__ == "__main__":
    main()
