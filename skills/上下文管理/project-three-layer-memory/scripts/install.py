#!/usr/bin/env python3
"""Install project memory locally and optionally enroll Codex global instructions."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

SKILL_DIR = Path(__file__).resolve().parent.parent
NAME = "project-three-layer-memory"
START = "<!-- project-three-layer-memory:global:start -->"
END = "<!-- project-three-layer-memory:global:end -->"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError(f"Refusing a symlink instruction file: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return path.read_bytes() if path.exists() else None


def safe_children(root: Path, target: Path) -> None:
    target.relative_to(root)
    for path in [target, *target.parents]:
        if path == root:
            break
        if path.is_symlink():
            raise ValueError(f"Refusing a symlink installation path: {path}")


def inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"Skill package must contain ordinary files: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    return files


def managed(text: str, replacement: str | None) -> str:
    a, b = text.count(START), text.count(END)
    if a != b or a > 1:
        raise ValueError("Malformed or repeated global memory markers; inspect the file before retrying")
    if a:
        left = text.index(START)
        right = text.index(END) + len(END)
        if right <= left:
            raise ValueError("Global memory markers are out of order")
        return text[:left] + (replacement or "") + text[right:]
    if replacement is None:
        return text
    separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + separator + replacement + "\n"


def global_block(skill: Path) -> str:
    if any(c in str(skill) for c in "\r\n`"):
        raise ValueError("Skill path cannot contain newlines or backticks")
    return f"""{START}
## Project memory defaults

When beginning substantive work in a clearly identified project, use the
`project-three-layer-memory` Skill at `{skill / 'SKILL.md'}`.
This applies to software, research, courses, writing and client projects.

- Resolve the actual project/workspace root. Never treat a user home, Documents,
  a collection of projects, or a temporary attachment directory as one project.
  For non-Git work use the explicitly opened project folder; do not guess its
  parent from an arbitrary subdirectory. If ambiguous, clarify only the root.
- Respect the user's scope and local instructions. A `.project-memory-disabled`
  file at the project root, a local opt-out, read-only review, or a simple question
  without ongoing project work means do not initialize or write memory.
- Inspect existing context/progress/procedure/decision files. Reuse them through
  the Skill's explicit mappings instead of creating competing sources of truth.
  For a new project without these files, initialize its project-local memory on
  the first authorized working task; this enrollment authorizes that setup.
- Read the concise project context and current handoff before continuing. Load
  procedures and past events only when relevant. Verify stale state against the
  current artifacts; cite paths when relying on previous work.
- At meaningful progress or handoff, save the goal, observed results with
  evidence, remaining work, blockers and next action in the project. Already
  authorized work and observed facts do not need repeated permission to record.
  Mark assumptions and proposals as pending; never invent completion or approval.
- Keep each project's memory in that project. Do not copy secrets, private
  personal profiles, unrelated project data or whole conversations into it.

This is a default Agent workflow, not a background watcher. A folder created
outside Codex is initialized only when Codex actually starts working there.
Instruction changes take effect on a new run/session; do not claim hot reload.
{END}"""


@contextlib.contextmanager
def lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        path.unlink()


def write_atomic(path: Path, content: bytes, previous: bytes | None) -> None:
    if read(path) != previous:
        raise ValueError(f"File changed since inspection; rerun the command: {path}")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    descriptor, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run(args: argparse.Namespace) -> dict:
    home = Path(args.home).expanduser().resolve() if args.home else Path.home().resolve()
    codex_default = os.environ.get("CODEX_HOME") if not args.home else None
    codex_home = Path(args.codex_home or codex_default or home / ".codex").expanduser().resolve()
    if codex_home in {Path(codex_home.anchor), home}:
        raise ValueError("Codex home must be a dedicated configuration directory")
    if args.disable_global and (args.enable_global or args.global_only or args.scope == "project"):
        raise ValueError("--disable-global cannot be combined with installation/global-enrollment options")
    if args.global_only and not args.enable_global:
        raise ValueError("--global-only requires --enable-global")
    if args.scope == "project":
        if args.enable_global:
            raise ValueError("Global enrollment requires a user-level installation")
        if not args.project:
            raise ValueError("--scope project requires --project")
        root = Path(args.project).expanduser().resolve()
        broad = {Path(root.anchor), home, home / "Documents", home / "Desktop", home / "Downloads"}
        if root in broad or not root.is_dir():
            raise ValueError("Choose an existing, specific project folder")
    else:
        root = home
    destination = root / ".agents" / "skills" / NAME
    safe_children(root, destination.parent)
    active_skill = SKILL_DIR if args.global_only else destination
    result: dict = {"ok": True, "dry_run": args.dry_run, "actions": []}
    source_hashes = inventory(SKILL_DIR)
    if not (SKILL_DIR / "scripts/project_memory.py").is_file() or "SKILL.md" not in source_hashes:
        raise ValueError("Incomplete Skill package")
    if not args.disable_global and not args.global_only:
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() and destination.resolve() != SKILL_DIR:
                raise ValueError(f"Existing Skill symlink points to another source: {destination}")
            if not destination.is_dir() or inventory(destination.resolve()) != source_hashes:
                raise ValueError(f"Different Skill already installed; review an update before replacing: {destination}")
            install_action = "already_installed"
        else:
            safe_children(root, destination)
            install_action = "install"
        result["actions"].append({"action": install_action, "path": str(destination)})
    else:
        install_action = "skip"

    updates = []
    originals = {}
    if args.enable_global or args.disable_global:
        # Inspect both files. On removal clear our block from either file, since an
        # override may have been added after enrollment. Never remove other text.
        override = codex_home / "AGENTS.override.md"
        base = codex_home / "AGENTS.md"
        originals = {path: read(path) for path in (override, base)}
        effective = override if originals[override] and originals[override].strip() else base
        targets = list(originals) if args.disable_global else [effective]
        for path in targets:
            before = originals[path]
            text = (before or b"").decode("utf-8")
            if args.disable_global and START not in text and END not in text:
                continue
            after = managed(text, None if args.disable_global else global_block(active_skill)).encode("utf-8")
            if args.enable_global and len(after) > args.instruction_budget:
                raise ValueError(
                    f"Global instructions would be {len(after)} bytes, exceeding the declared "
                    f"Codex instruction budget ({args.instruction_budget}). Shorten the global "
                    "file or configure a larger project_doc_max_bytes in Codex and pass the same "
                    "value via --instruction-budget. No enrollment was performed."
                )
            if after != (before or b""):
                updates.append((path, before, after))
                result["actions"].append({"action": "remove_global_block" if args.disable_global else "enroll_global", "path": str(path)})
        result["effective_instructions"] = str(effective)
        result["activation"] = "new_codex_run_or_session"
        result["instruction_budget"] = args.instruction_budget
        result["budget_scope"] = "global_file_only; project instructions share the Codex budget"
    if args.dry_run:
        return result

    if install_action == "install":
        destination.parent.mkdir(parents=True, exist_ok=True)
        with lock(destination.parent / f".{NAME}.install.lock"):
            if destination.exists() or destination.is_symlink():
                raise ValueError("Installation target changed; rerun after inspection")
            staging = Path(tempfile.mkdtemp(prefix=f".{NAME}.", dir=destination.parent))
            try:
                shutil.copytree(SKILL_DIR, staging / NAME, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                if inventory(staging / NAME) != source_hashes:
                    raise ValueError("Source changed while copying; rerun installation")
                os.replace(staging / NAME, destination)
            finally:
                shutil.rmtree(staging)

    backups = []
    if updates or args.enable_global:
        with lock(codex_home / ".project-memory-install.lock"):
            # The other instruction file can become effective between inspection
            # and this lock. Verify both snapshots, even on an idempotent run.
            for path, before in originals.items():
                if read(path) != before:
                    raise ValueError(f"Instructions changed; rerun after inspection: {path}")
            for path, before, after in updates:
                if before is not None:
                    backup = path.with_name(path.name + f".project-memory-backup-{digest(before)[:12]}")
                    if backup.is_symlink():
                        raise ValueError(f"Refusing symlink backup: {backup}")
                    if backup.exists() and backup.read_bytes() != before:
                        raise ValueError(f"Backup conflict: {backup}")
                    if not backup.exists():
                        with backup.open("xb") as handle:
                            handle.write(before)
                        os.chmod(backup, 0o600)
                    backups.append(str(backup))
                write_atomic(path, after, before)
    result["backups"] = backups
    result["global_enabled"] = args.enable_global
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--project", help="Exact existing project root for --scope project")
    parser.add_argument("--home", help="Home-like root for installation/testing; defaults to the user's home")
    parser.add_argument("--codex-home", help="Codex config root; otherwise CODEX_HOME or ~/.codex")
    parser.add_argument("--enable-global", action="store_true", help="Enroll defaults for future Codex projects")
    parser.add_argument("--global-only", action="store_true", help="Enroll this already managed Skill without copying it")
    parser.add_argument("--disable-global", action="store_true", help="Remove only this Skill's global instruction block")
    parser.add_argument("--instruction-budget", type=int, default=32768, help="Actual Codex project_doc_max_bytes budget (default 32768); project rules share it")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.instruction_budget < 1:
        parser.error("--instruction-budget must be positive")
    try:
        result = run(args)
    except (OSError, ValueError, UnicodeError) as exc:
        # No document contents, environment values or secrets are printed.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
