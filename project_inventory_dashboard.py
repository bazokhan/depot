import ctypes
import hashlib
import json
import os
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
DEFAULT_ROOTS = [r"D:\OneDrive\projects", r"D:\projects"]

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".log",
    ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh",
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

FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_PINNED = 0x00080000
FILE_ATTRIBUTE_UNPINNED = 0x00100000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


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
        result = subprocess.run(["git", "-C", project_path] + args, capture_output=True, text=True, timeout=6, check=False)
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


def render_root_editor() -> Tuple[bool, List[str]]:
    st.header("Scan Controls")
    if "scan_roots_list" not in st.session_state:
        st.session_state["scan_roots_list"] = [r for r in DEFAULT_ROOTS if os.path.isdir(r)] or DEFAULT_ROOTS[:1]
    roots = list(st.session_state["scan_roots_list"])

    st.caption("Add one or many roots. Paths can be typed manually or selected with Browse.")
    remove_index = None
    for idx in range(len(roots)):
        cols = st.columns([7, 1.4, 1.2])
        roots[idx] = cols[0].text_input(f"Root {idx + 1}", value=roots[idx], key=f"scan_root_{idx}")
        if cols[1].button("Browse", key=f"browse_{idx}", use_container_width=True):
            chosen = pick_folder(roots[idx] or r"D:\\")
            if chosen:
                roots[idx] = chosen
                st.session_state["scan_roots_list"] = roots
                st.rerun()
        if cols[2].button("Remove", key=f"remove_{idx}", use_container_width=True, disabled=len(roots) == 1):
            remove_index = idx

    if remove_index is not None and len(roots) > 1:
        roots.pop(remove_index)
        st.session_state["scan_roots_list"] = roots
        st.rerun()

    if st.button("Add another root", use_container_width=True):
        roots.append("")
        st.session_state["scan_roots_list"] = roots
        st.rerun()

    st.session_state["scan_roots_list"] = roots
    valid = [r.strip() for r in roots if r.strip()]
    if not valid:
        st.warning("Add at least one root path.")
    st.caption("The scan checks immediate child folders under each root, recursively.")
    return st.button("Run Full Scan", type="primary", use_container_width=True), valid


def apply_inventory_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Project Inventory")

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

    view = apply_inventory_filters(df)
    table = view.copy()
    table["Git"] = table["has_git_tree"].map(lambda v: bool_icon(v, "🌿", "—"))
    table["Remote"] = table["has_remote"].map(lambda v: bool_icon(v, "☁️", "—"))
    table["Remote URL"] = table["remote_url"].map(remote_to_web_url)
    table["Open folder"] = table["project_path"].map(path_to_file_url)
    table["Empty"] = table["is_empty"].map(lambda v: bool_icon(v, "📭", "—"))
    table["Both roots"] = table["in_multiple_roots"].map(lambda v: bool_icon(v, "🔁", "—"))
    table["Duplicates"] = table["duplicate_group_size"].map(lambda n: "🧬" if int(n) > 1 else "—")
    table["Logical size"] = table["logical_size_bytes"].map(format_bytes)
    table["On-disk size"] = table["allocated_size_bytes"].map(format_bytes)
    table["Errors"] = table["scan_errors"].map(lambda n: "⚠️" if int(n) > 0 else "—")

    show = table[
        [
            "project_name", "source_root", "Open folder", "Git", "Remote", "remote_owner", "Remote URL", "Empty", "Both roots", "Duplicates",
            "total_files", "total_dirs", "Logical size", "On-disk size", "last_commit_date",
            "last_file_modified_utc", "top_languages", "framework_hints", "Errors", "project_path",
        ]
    ].rename(
        columns={
            "project_name": "Project",
            "source_root": "Root",
            "remote_owner": "Remote owner",
            "total_files": "Files",
            "total_dirs": "Folders",
            "last_commit_date": "Last commit",
            "last_file_modified_utc": "Last file update",
            "top_languages": "Languages",
            "framework_hints": "Framework hints",
            "project_path": "Path",
        }
    )

    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Project": st.column_config.TextColumn(width="medium"),
            "Root": st.column_config.TextColumn(width="medium"),
            "Path": st.column_config.TextColumn(width="large"),
            "Open folder": st.column_config.LinkColumn(width="small", display_text="📂 Open"),
            "Remote URL": st.column_config.LinkColumn(width="large"),
            "Remote owner": st.column_config.TextColumn(width="medium"),
            "Files": st.column_config.NumberColumn(format="%d"),
            "Folders": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(f"Rows shown: {len(show)}")
    return view


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
    st.markdown("### File Preview (Read-Only)")
    try:
        st_info = os.stat(file_path)
        attrs = getattr(st_info, "st_file_attributes", 0)
        st.caption(f"`{file_path}`")
        st.caption(f"Size: {format_bytes(st_info.st_size)} | State: {file_state_from_attrs(attrs)}")
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
        st.info("File larger than 2MB. Preview skipped for responsiveness.")
        return

    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        st.error(f"Could not read file content: {exc}")
        return

    if suffix == ".md":
        st.markdown(content)
    else:
        st.code(content)


def find_root_readme(project_path: str) -> Optional[Path]:
    candidates = ["README.md", "Readme.md", "readme.md", "README.txt", "readme.txt", "README"]
    for name in candidates:
        p = Path(project_path) / name
        if p.exists() and p.is_file():
            return p
    return None


def render_readme_preview(project_path: str) -> None:
    readme = find_root_readme(project_path)
    if not readme:
        st.info("No README found in this project root.")
        return

    with st.expander("README (root)", expanded=True):
        st.caption(f"`{readme}`")
        try:
            size = readme.stat().st_size
            if size > 2 * 1024 * 1024:
                st.info("README is larger than 2MB; preview skipped.")
                return
            content = readme.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            st.error(f"Could not load README: {exc}")
            return

        if readme.suffix.lower() == ".md":
            st.markdown(content)
        else:
            st.code(content)


def render_explorer(project_path: str) -> None:
    st.subheader("Read-Only Explorer")
    nav_key = f"nav::{project_path}"
    if nav_key not in st.session_state:
        st.session_state[nav_key] = project_path
    current_path = st.session_state[nav_key]

    if not os.path.isdir(current_path) or os.path.commonpath([project_path, current_path]) != project_path:
        st.session_state[nav_key] = project_path
        current_path = project_path

    c1, c2 = st.columns([1, 8])
    with c1:
        if current_path != project_path and st.button("Up", key=f"up::{project_path}", use_container_width=True):
            st.session_state[nav_key] = os.path.dirname(current_path)
            st.rerun()
    with c2:
        st.text_input("Current folder", value=current_path, disabled=True, key=f"path::{project_path}")

    folders, files, errors = list_folder_entries(current_path)
    if errors:
        st.warning("Some paths could not be read.")
        for err in errors[:4]:
            st.caption(err)

    st.markdown("**Folders**")
    if folders:
        folder_options = [f.path for f in folders[:500]]
        selected_folder = st.selectbox(
            "Subfolders",
            folder_options,
            format_func=lambda p: f"📁 {os.path.basename(p)}",
            key=f"folder_select::{current_path}",
        )
        if st.button("Open selected folder", key=f"open_folder::{current_path}"):
            st.session_state[nav_key] = selected_folder
            st.rerun()
    else:
        st.caption("No subfolders.")

    st.markdown("**Files**")
    if files:
        file_options = [f.path for f in files[:500]]
        selected_file = st.selectbox(
            "Select file to preview",
            file_options,
            format_func=lambda p: f"📄 {os.path.basename(p)}",
            key=f"file_select::{current_path}",
        )
        action_cols = st.columns([1, 1, 3])
        if action_cols[0].button("Open file", key=f"open_file::{current_path}", use_container_width=True):
            open_in_explorer(selected_file)
        if action_cols[1].button("Open folder", key=f"open_file_folder::{current_path}", use_container_width=True):
            open_in_explorer(str(Path(selected_file).parent))
        render_file_preview(selected_file)
    else:
        st.caption("No files.")


def render_git_panel(row: pd.Series) -> None:
    st.subheader("Git Details")
    if int(row["has_git_tree"]) != 1:
        st.info("No git repository detected in this project tree.")
        return

    st.write(f"Remote: `{row.get('remote_url') or '-'}`")
    remote_web = remote_to_web_url(row.get("remote_url"))
    if remote_web:
        st.markdown(f"[Open remote repository]({remote_web})")
        if st.button("Open remote in browser", key=f"open_remote::{row.get('project_path')}"):
            webbrowser.open(remote_web, new=2)
    st.write(f"Owner: `{row.get('remote_owner') or '-'}`")
    st.write(f"Branch: `{row.get('default_branch') or '-'}`")
    st.write(f"Last commit: `{row.get('last_commit_date') or '-'}` by `{row.get('last_commit_author') or '-'}`")

    recent = run_git(str(row["project_path"]), ["log", "-5", "--pretty=%h | %ad | %an | %s", "--date=short"])
    if recent:
        st.markdown("**Recent commits**")
        for line in recent.splitlines():
            st.code(line)


def main() -> None:
    st.set_page_config(page_title="Project Inventory Dashboard", page_icon="🗂️", layout="wide")
    st.title("🗂️ Project Inventory Dashboard")
    st.caption("Read-only review workspace for old projects. No delete/move/edit actions are included.")

    initialize_db(DB_PATH)

    with st.sidebar:
        scan_now, roots = render_root_editor()

    if scan_now:
        rows = scan_roots(roots)
        save_scan(rows, DB_PATH)
        st.success(f"Scan complete: {len(rows)} projects indexed.")

    df = load_projects(DB_PATH)
    filtered = render_inventory(df)
    if filtered.empty:
        return

    st.markdown("---")
    st.subheader("Project Drilldown")
    selected_path = st.selectbox(
        "Choose project",
        filtered["project_path"].tolist(),
        format_func=lambda p: f"{Path(p).name} ({p})",
    )
    selected = filtered[filtered["project_path"] == selected_path].iloc[0]

    left, right = st.columns([2, 1])
    with left:
        render_explorer(str(selected["project_path"]))
    with right:
        render_readme_preview(str(selected["project_path"]))
        quick_cols = st.columns([1, 1])
        if quick_cols[0].button("Open project in Explorer", use_container_width=True):
            open_in_explorer(str(selected["project_path"]))
        if quick_cols[1].button("Open root in Explorer", use_container_width=True):
            open_in_explorer(str(selected["source_root"]))
        st.subheader("Metadata")
        st.write(f"**Name**: {selected.get('project_name')}")
        st.write(f"**Root**: {selected.get('source_root')}")
        st.write(f"**Git tree**: {bool_icon(int(selected.get('has_git_tree', 0)), '🌿 Yes', 'No')}")
        st.write(f"**Remote**: {bool_icon(int(selected.get('has_remote', 0)), '☁️ Yes', 'No')}")
        st.write(f"**Empty**: {bool_icon(int(selected.get('is_empty', 0)), '📭 Yes', 'No')}")
        st.write(f"**Files**: {selected.get('total_files')}")
        st.write(f"**Folders**: {selected.get('total_dirs')}")
        st.write(f"**Logical size**: {format_bytes(selected.get('logical_size_bytes'))}")
        st.write(f"**On-disk size**: {format_bytes(selected.get('allocated_size_bytes'))}")
        st.write(f"**Last file update**: {selected.get('last_file_modified_utc')}")
        st.write(f"**Languages**: {selected.get('top_languages') or '-'}")
        st.write(f"**Framework hints**: {selected.get('framework_hints') or '-'}")
        st.write(f"**OneDrive states**: `{selected.get('onedrive_states')}`")
        render_git_panel(selected)


if __name__ == "__main__":
    main()
