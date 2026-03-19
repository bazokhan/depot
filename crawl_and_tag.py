#!/usr/bin/env python3
"""
Crawl project directories and auto-write .repo-meta.json with classification metadata.

Implements the specification in crawl-and-tag-prompt.md.
- Reads depot_config.json for scan_roots and custom_brands (falls back to built-in defaults)
- Crawls each root, gathers README, package manifests, git info
- Classifies projects using heuristics and decision rules
- Writes .repo-meta.json only when safe (never overwrites meaningfully-filled existing meta)
- Optionally syncs written meta to depot.db

Usage:
  python crawl_and_tag.py              # Run with config from depot_config.json
  python crawl_and_tag.py --dry-run    # Report what would be written, don't write
  python crawl_and_tag.py --force      # Overwrite even projects with existing meta
  python crawl_and_tag.py --sync-db    # Also update depot.db for written projects
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Paths to skip entirely (infrastructure, not products)
SKIP_PATH_SUFFIXES = [
    "trugraph.io",
    "landing-page",
    "blog",
    "gamercury-website",
    "vault",
    "personal-profile",
]

# Folder names to skip during crawl (same as depot)
SKIP_FOLDER_NAMES = {"node_modules", ".venv", "__pycache__", ".next", "dist", "build", "vendor", "target"}

# Root -> brand mapping (from prompt)
ROOT_TO_BRAND: Dict[str, str] = {
    "D:/Trugraph": "trugraph",
    "D:/Gamercury": "gamercury",
    "D:/AI": "personal",
    "D:/Code": "personal",
    "D:/projects": "personal",
}

# Default roots (used when depot_config.json has no scan_roots)
DEFAULT_ROOTS = ["D:/Trugraph", "D:/Gamercury", "D:/AI", "D:/Code", "D:/projects"]

REPO_META_FILENAME = ".repo-meta.json"

USER_META_DEFAULTS: Dict[str, Any] = {
    "hidden": False,
    "status": "",
    "pinned": False,
    "tags": [],
    "category": "",
    "description": "",
    "notes": "",
    "display_name": "",
    "brand": "",
    "type": "",
    "ownership": "",
    "portfolio": [],
    "featured": False,
    "priority": 50,
    "live_url": "",
    "demo_url": "",
}

# Technology -> tags mapping
LANG_TAGS: Dict[str, str] = {
    ".ts": "typescript", ".tsx": "typescript", ".js": "nodejs", ".jsx": "nodejs",
    ".py": "python", ".rs": "rust", ".go": "go",
}

MARKER_TO_TYPE: Dict[str, str] = {
    "package.json": "library",
    "pyproject.toml": "library",
    "Cargo.toml": "library",
    "go.mod": "library",
    "next.config.js": "website",
    "vite.config.js": "website",
}

GAME_INDICATORS = ["godot", "unity", "phaser", "game", "puzzle", "adventure", "rpg", "engine"]


def _run_git(project_path: str, args: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", project_path] + args,
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


def _parse_remote_owner(remote_url: Optional[str]) -> Optional[str]:
    if not remote_url:
        return None
    url = remote_url.replace(".git", "").replace(":", "/")
    for host in ["github.com", "gitlab.com", "bitbucket.org"]:
        if host in url:
            parts = url.split("/")
            for i, p in enumerate(parts):
                if host in p and i + 1 < len(parts):
                    return parts[i + 1]
    return None


def _remote_to_web_url(remote_url: Optional[str]) -> Optional[str]:
    if not remote_url:
        return None
    r = remote_url.strip()
    if r.startswith(("http://", "https://")):
        return r[:-4] if r.endswith(".git") else r
    if r.startswith("git@") and ":" in r:
        host_part, repo_part = r.split(":", 1)
        host = host_part.replace("git@", "").strip("/")
        repo = repo_part.strip("/").replace(".git", "")
        if host and repo:
            return f"https://{host}/{repo}"
    return None


def _load_config() -> Dict:
    config_path = Path(__file__).with_name("depot_config.json")
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get_roots() -> List[str]:
    cfg = _load_config()
    roots = cfg.get("scan_roots", [])
    if isinstance(roots, list) and roots:
        return [str(r).strip() for r in roots if str(r).strip()]
    return [r for r in DEFAULT_ROOTS if os.path.isdir(r)]


def _get_brands() -> List[str]:
    cfg = _load_config()
    brands = cfg.get("custom_brands", [])
    if isinstance(brands, list) and brands:
        return [str(b).strip() for b in brands if str(b).strip()]
    return ["trugraph", "gamercury", "personal"]


def _read_readme(project_path: str) -> Optional[str]:
    for name in ("README.md", "README.rst", "README.txt"):
        p = Path(project_path) / name
        if p.exists() and p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:3000]
            except Exception:
                return None
    return None


def _parse_package_json(project_path: str) -> Optional[dict]:
    p = Path(project_path) / "package.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_pyproject(project_path: str) -> Optional[dict]:
    p = Path(project_path) / "pyproject.toml"
    if not p.exists():
        return None
    try:
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return None
        with open(p, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def _parse_cargo_toml(project_path: str) -> Optional[dict]:
    p = Path(project_path) / "Cargo.toml"
    if not p.exists():
        return None
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        # Minimal TOML parse for [package] name, version, description
        in_package = False
        out = {}
        for line in content.splitlines():
            line = line.strip()
            if line == "[package]":
                in_package = True
                continue
            if in_package and line.startswith("["):
                break
            if in_package and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"\'')
                if k in ("name", "version", "description"):
                    out[k] = v
        return out if out else None
    except Exception:
        return None


def _parse_go_mod(project_path: str) -> Optional[dict]:
    p = Path(project_path) / "go.mod"
    if not p.exists():
        return None
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        out = {}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("module "):
                out["module"] = line[6:].strip()
            elif line.startswith("//") or not line:
                continue
        return out if out else None
    except Exception:
        return None


def _get_top_level_folders(project_path: str) -> List[str]:
    try:
        return [
            e.name for e in os.scandir(project_path)
            if e.is_dir() and e.name not in SKIP_FOLDER_NAMES and not e.name.startswith(".")
        ][:20]
    except Exception:
        return []


def gather_project_info(project_path: str, source_root: str) -> Dict[str, Any]:
    """Gather README, manifests, folder structure, git info for a project."""
    project_name = os.path.basename(project_path)
    normalized_root = source_root.replace("\\", "/").rstrip("/")

    readme = _read_readme(project_path)
    pkg = _parse_package_json(project_path)
    pyproj = _parse_pyproject(project_path)
    cargo = _parse_cargo_toml(project_path)
    go_mod = _parse_go_mod(project_path)
    folders = _get_top_level_folders(project_path)

    is_git = os.path.exists(os.path.join(project_path, ".git"))
    remote_url = _run_git(project_path, ["remote", "get-url", "origin"]) if is_git else None
    git_log = _run_git(project_path, ["log", "--oneline", "-10"]) if is_git else None
    remote_owner = _parse_remote_owner(remote_url)
    live_url = _remote_to_web_url(remote_url)

    # npm homepage from package.json
    npm_homepage = None
    if pkg:
        homepage = pkg.get("homepage") or pkg.get("repository")
        if isinstance(homepage, str) and homepage.startswith("http"):
            npm_homepage = homepage
        elif isinstance(homepage, dict) and homepage.get("url"):
            url = homepage["url"]
            if url.startswith(("http://", "https://")):
                npm_homepage = url
            elif "github.com" in url:
                npm_homepage = url.replace("git+", "").replace(".git", "").replace("git@github.com:", "https://github.com/")

    return {
        "project_name": project_name,
        "project_path": project_path,
        "source_root": normalized_root,
        "readme": readme,
        "package_json": pkg,
        "pyproject": pyproj,
        "cargo": cargo,
        "go_mod": go_mod,
        "top_folders": folders,
        "is_git": is_git,
        "remote_url": remote_url,
        "remote_owner": remote_owner,
        "git_log": git_log,
        "live_url": live_url or npm_homepage,
        "brand_from_path": ROOT_TO_BRAND.get(normalized_root, "personal"),
    }


def classify_project(info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify project using heuristics from crawl-and-tag-prompt.md.
    Returns a .repo-meta.json-compatible dict.
    """
    meta = dict(USER_META_DEFAULTS)
    project_name = info["project_name"]
    readme = (info.get("readme") or "").lower()
    pkg = info.get("package_json") or {}
    pyproj = info.get("pyproject") or {}
    cargo = info.get("cargo") or {}
    go_mod = info.get("go_mod") or {}
    folders = info.get("top_folders") or []
    folder_names = " ".join(folders).lower()
    path_lower = info["project_path"].lower()
    brand_from_path = info.get("brand_from_path", "personal")
    source_root = info.get("source_root", "")

    # --- Decision rule 1: Fork/clone with no meaningful commits from me ---
    # Heuristic: remote owner exists and project name suggests fork (contains original repo name often)
    # Simpler: if D:/AI and remote_owner is not "me" - we don't know "me", so skip this for now.
    # Use: folder name contains "test", "temp", "scratch", "demo", "example" -> experiment
    name_lower = project_name.lower()
    if any(x in name_lower for x in ["test", "temp", "scratch", "demo", "example"]):
        meta["status"] = "archived"
        meta["type"] = "experiment"
        meta["priority"] = 15
        meta["portfolio"] = []
        meta["description"] = f"Exploratory project: {project_name}"
        meta["brand"] = brand_from_path
        meta["ownership"] = "personal"
        return meta

    # --- Brand ---
    meta["brand"] = brand_from_path

    # --- Type ---
    # Game indicators
    is_game = any(
        g in readme or g in folder_names or g in path_lower or g in name_lower
        for g in GAME_INDICATORS
    )
    if is_game or "D:/Gamercury" in source_root:
        meta["type"] = "game"
        meta["category"] = "Games"
    elif pkg:
        # Check package.json for keywords
        pkg_name = (pkg.get("name") or "").lower()
        pkg_desc = (pkg.get("description") or "").lower()
        pkg_keywords = [k.lower() for k in (pkg.get("keywords") or []) if isinstance(k, str)]
        if any(g in pkg_name or g in pkg_desc or any(g in kw for kw in pkg_keywords) for g in GAME_INDICATORS):
            meta["type"] = "game"
            meta["category"] = "Games"
        elif "next" in pkg.get("dependencies", {}) or "next" in str(pkg.get("devDependencies", {})):
            meta["type"] = "website"
            meta["category"] = "Web Apps"
        elif pkg.get("bin") or "cli" in pkg_name or "cli" in pkg_desc:
            meta["type"] = "tool"
            meta["category"] = "Developer Tools"
        else:
            meta["type"] = "library"
            meta["category"] = "Libraries"
    elif pyproj:
        proj = pyproj.get("project", {}) or {}
        if isinstance(proj, dict):
            desc = (proj.get("description") or "").lower()
            if "cli" in desc or "tool" in desc:
                meta["type"] = "tool"
                meta["category"] = "Developer Tools"
            else:
                meta["type"] = "library"
                meta["category"] = "Libraries"
    elif cargo or go_mod:
        meta["type"] = "library"
        meta["category"] = "Libraries"
    else:
        # Fallback from folder structure
        if "src" in folders or "lib" in folders:
            meta["type"] = "library"
        elif "app" in folders or "pages" in folders or "components" in folders:
            meta["type"] = "website"
        else:
            meta["type"] = "experiment"
            meta["category"] = "Experiments"

    # --- Tags ---
    tags: Set[str] = set()
    if pkg:
        tags.add("nodejs")
        if any(k in str(pkg.get("dependencies", {})) for k in ["react", "next"]):
            tags.update(["react", "nextjs"])
    if pyproj or (Path(info["project_path"]) / "requirements.txt").exists():
        tags.add("python")
    if cargo:
        tags.add("rust")
    if go_mod:
        tags.add("go")
    if meta["type"] == "game":
        tags.add("game")
    if meta["type"] == "library":
        tags.add("library")
    if meta["type"] == "tool":
        tags.add("tool")
    if meta["type"] == "website":
        tags.add("web")
    meta["tags"] = sorted(tags)

    # --- Description ---
    desc = ""
    if pkg and pkg.get("description"):
        desc = str(pkg["description"])[:120]
    elif pyproj:
        proj = pyproj.get("project", {}) or {}
        if isinstance(proj, dict) and proj.get("description"):
            desc = str(proj["description"])[:120]
    elif cargo and cargo.get("description"):
        desc = str(cargo["description"])[:120]
    elif readme:
        # First line of readme often is a title/description
        first_line = (info.get("readme") or "").split("\n")[0].strip()
        if first_line and not first_line.startswith("#") and len(first_line) < 120:
            desc = first_line[:120]
        else:
            desc = f"{project_name.replace('-', ' ').replace('_', ' ').title()} project."
    else:
        desc = f"{project_name.replace('-', ' ').replace('_', ' ').title()}."
    meta["description"] = desc.strip() or meta["description"]

    # --- Status ---
    if not info.get("is_git") and not readme and not pkg and not pyproj and not cargo and not go_mod:
        meta["status"] = "abandoned"
        meta["priority"] = 10
    else:
        meta["status"] = "active"  # Default; could refine with git log recency

    # --- Ownership ---
    meta["ownership"] = "personal"

    # --- Portfolio ---
    portfolios: List[str] = []
    if brand_from_path == "trugraph" and meta["type"] in ("library", "tool") and meta["status"] not in ("abandoned", ""):
        portfolios.append("trugraph")
        portfolios.append("personal-profile")
        if meta["type"] == "library" and (pkg or pyproj or cargo or go_mod):
            portfolios.append("trugraph-landing")
    elif brand_from_path == "gamercury" and meta["type"] == "game" and meta["status"] not in ("abandoned", ""):
        portfolios.append("gamercury")
        portfolios.append("personal-profile")
    elif brand_from_path == "personal" and meta["type"] != "experiment" and meta["status"] not in ("abandoned", ""):
        portfolios.append("personal-profile")
    meta["portfolio"] = list(dict.fromkeys(portfolios))

    # --- live_url ---
    if info.get("live_url"):
        meta["live_url"] = info["live_url"]
    elif pkg and pkg.get("name"):
        meta["live_url"] = meta.get("live_url") or f"https://www.npmjs.com/package/{pkg['name']}"

    # --- priority ---
    if meta["type"] == "experiment" or meta["status"] == "abandoned":
        meta["priority"] = min(meta.get("priority", 50), 30)

    return meta


def is_meaningfully_filled(meta: Dict[str, Any]) -> bool:
    """True if description, brand, or portfolio already have non-empty values."""
    return bool(
        (meta.get("description") or "").strip()
        or (meta.get("brand") or "").strip()
        or (meta.get("portfolio") or [])
    )


def read_existing_meta(project_path: str) -> Optional[Dict[str, Any]]:
    p = Path(project_path) / REPO_META_FILENAME
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def merge_meta(existing: Dict[str, Any], classified: Dict[str, Any]) -> Dict[str, Any]:
    """Keep existing non-default values, fill in missing from classified."""
    out = dict(USER_META_DEFAULTS)
    for key, default in USER_META_DEFAULTS.items():
        existing_val = existing.get(key)
        classified_val = classified.get(key)
        if existing_val is not None and existing_val != default:
            out[key] = existing_val
        elif classified_val is not None:
            out[key] = classified_val
    return out


def write_repo_meta(project_path: str, meta: Dict[str, Any]) -> bool:
    p = Path(project_path) / REPO_META_FILENAME
    output = {k: meta.get(k, v) for k, v in USER_META_DEFAULTS.items()}
    try:
        p.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        print(f"  ERROR: Could not write {p}: {e}", file=sys.stderr)
        return False


def sync_meta_to_db(project_path: str, meta: Dict[str, Any], db_path: Path) -> bool:
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
            return conn.total_changes > 0
    except Exception as e:
        print(f"  ERROR: Could not sync to DB: {e}", file=sys.stderr)
        return False


def should_skip_path(project_path: str) -> bool:
    normalized = project_path.replace("\\", "/")
    name = os.path.basename(normalized)
    for suffix in SKIP_PATH_SUFFIXES:
        if name == suffix or normalized.endswith("/" + suffix):
            return True
    return False


def collect_projects(roots: List[str]) -> List[Tuple[str, str]]:
    """Return list of (project_path, source_root)."""
    projects: List[Tuple[str, str]] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for item in sorted(os.listdir(root), key=str.lower):
                full = os.path.join(root, item)
                if not os.path.isdir(full):
                    continue
                if item in SKIP_FOLDER_NAMES or item.startswith("."):
                    continue
                if should_skip_path(full):
                    continue
                projects.append((full, root))
        except Exception as e:
            print(f"WARN: Could not list {root}: {e}", file=sys.stderr)
    return projects


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl projects and auto-write .repo-meta.json")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write files")
    parser.add_argument("--force", action="store_true", help="Overwrite even if meta already filled")
    parser.add_argument("--sync-db", action="store_true", help="Sync written meta to depot.db")
    args = parser.parse_args()

    roots = _get_roots()
    if not roots:
        print("No scan roots found. Add scan_roots to depot_config.json or ensure default paths exist.", file=sys.stderr)
        return 1

    print(f"Crawling roots: {roots}")
    projects = collect_projects(roots)
    print(f"Found {len(projects)} projects\n")

    db_path = Path(__file__).with_name("depot.db")
    written = 0
    skipped_filled = 0
    skipped_path = 0

    for project_path, source_root in projects:
        info = gather_project_info(project_path, source_root)
        classified = classify_project(info)
        existing = read_existing_meta(project_path)

        if existing and is_meaningfully_filled(existing) and not args.force:
            skipped_filled += 1
            print(f"{project_path}")
            print(f"  -> SKIPPED (existing meta with description/brand/portfolio)")
            continue

        if args.dry_run:
            print(f"{project_path}")
            print(f"  -> Would write: brand={classified.get('brand')}, type={classified.get('type')}, portfolio={classified.get('portfolio')}, priority={classified.get('priority')}")
            continue

        final = merge_meta(existing or {}, classified) if existing else classified
        if write_repo_meta(project_path, final):
            written += 1
            print(f"{project_path}")
            print(f"  -> Wrote .repo-meta.json: brand={final.get('brand')}, type={final.get('type')}, portfolio={final.get('portfolio')}, priority={final.get('priority')}")
            if args.sync_db and db_path.exists():
                if sync_meta_to_db(project_path, final, db_path):
                    print(f"  -> Synced to depot.db")

    print(f"\nDone. Written: {written}, Skipped (filled): {skipped_filled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
