#!/usr/bin/env python3
"""Install portable project memory and enroll the current Agent's rule entry."""
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


def global_block(skill: Path, agent: str = "codex") -> str:
    if any(c in str(skill) for c in "\r\n`"):
        raise ValueError("Skill path cannot contain newlines or backticks")
    return f"""{START}
## Project memory defaults

When beginning substantive work in a clearly identified project, use the
`project-three-layer-memory` Skill at `{skill / 'SKILL.md'}`.
This applies to software, research, courses, writing and client projects.
For project initialization use `init --project <exact-project-root> --agent {agent if agent in {'codex', 'claude', 'gemini'} else 'generic'}`.
Claude Code and Gemini CLI use their native project rule import bridges;
all hosts share the same project-local memory files.

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
outside the Agent is initialized only when the Agent actually starts working there.
Instruction changes take effect on a new run/session; do not claim hot reload.
{END}"""


def layout(args: argparse.Namespace, home: Path) -> tuple[Path, Path, list[Path], dict[Path, bytes | None]]:
    """Return config root, user Skill root, global candidates and config snapshots."""
    agent = args.agent
    if args.codex_home and agent != "codex":
        raise ValueError("--codex-home is specific to --agent codex")
    if args.codex_home and args.agent_home:
        raise ValueError("Use only one of --agent-home and --codex-home")
    use_env = not args.home and not args.agent_home
    snapshots = {}
    if agent == "codex":
        config = Path(args.codex_home or args.agent_home or (os.environ.get("CODEX_HOME") if use_env else None) or home / ".codex").expanduser().resolve()
        skills = home / ".agents" / "skills"
        files = [config / "AGENTS.override.md", config / "AGENTS.md"]
    elif agent == "claude":
        config = Path(args.agent_home or (os.environ.get("CLAUDE_CONFIG_DIR") if use_env else None) or home / ".claude").expanduser().resolve()
        skills = config / "skills"
        files = [config / "CLAUDE.md"]
    elif agent == "gemini":
        gemini_base = Path(os.environ.get("GEMINI_CLI_HOME") or home) if use_env else home
        config = Path(args.agent_home or gemini_base / ".gemini").expanduser().resolve()
        skills = config / "skills"
        settings = config / "settings.json"
        snapshots[settings] = read(settings)
        data = json.loads(snapshots[settings].decode("utf-8")) if snapshots[settings] else {}
        if not isinstance(data, dict) or not isinstance(data.get("context", {}), dict):
            raise ValueError("Gemini settings and context must be JSON objects")
        names = data.get("context", {}).get("fileName", "GEMINI.md")
        names = [names] if isinstance(names, str) else names
        if not isinstance(names, list) or not names:
            raise ValueError("Gemini context.fileName must be a name or non-empty name list")
        for name in names:
            if not isinstance(name, str) or name in {".", ".."} or not name or any(c in name for c in "/\\:\r\n"):
                raise ValueError("Gemini context.fileName must contain simple file names")
        files = [config / name for name in dict.fromkeys(names)]
    else:
        if args.agent_home:
            raise ValueError("--agent-home is for codex, claude or gemini; use --global-instructions for another host")
        config = home / ".agents"
        skills = home / (".cursor" if agent == "cursor" else ".agents") / "skills"
        files = []
    if config in {Path(config.anchor), home}:
        raise ValueError("Agent config root must be a dedicated directory")
    if args.global_instructions:
        if agent != "generic":
            raise ValueError("--global-instructions is for --agent generic; native hosts use their documented entries")
        # Preserve the final component so read() can reject symlink files.
        files = [Path(os.path.abspath(os.path.expanduser(args.global_instructions)))]
        config = files[0].parent
    return config, skills, files, snapshots


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
    config_root, user_skills, global_files, config_snapshots = layout(args, home)
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
        skill_parent = root / (".claude" if args.agent == "claude" else ".gemini" if args.agent == "gemini" else ".agents") / "skills"
    else:
        root = config_root if args.agent in {"claude", "gemini"} else home
        skill_parent = user_skills
    destination = skill_parent / NAME
    safe_children(root, destination.parent)
    active_skill = SKILL_DIR if args.global_only else destination
    result: dict = {"ok": True, "agent": args.agent, "dry_run": args.dry_run, "actions": []}
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
    originals = dict(config_snapshots)
    manual = args.agent in {"cursor", "generic"} and not global_files
    budget = args.instruction_budget if args.instruction_budget is not None else (32768 if args.agent == "codex" else None)
    if args.enable_global or args.disable_global:
        if manual:
            if args.disable_global:
                result.update({"global_enabled": None, "manual_action_required": True, "activation": "remove_the_managed_block_in_host_user_rules", "actions": [{"action": "manual_removal_required", "start_marker": START, "end_marker": END}]})
                return result
            export = Path(os.path.abspath(os.path.expanduser(args.rules_output))) if args.rules_output else home / ".agents" / "project-memory-user-rules.md"
            if not args.rules_output:
                safe_children(home, export)
            global_files = [export]
            result.update({"manual_action_required": True, "rules_output": str(export), "activation": "paste_into_cursor_user_rules" if args.agent == "cursor" else "configure_the_host_to_load_these_rules"})
        originals.update({path: read(path) for path in global_files})
        if args.agent == "codex":
            effective = global_files[0] if originals[global_files[0]] and originals[global_files[0]].strip() else global_files[1]
        else:
            effective = global_files[0]
        targets = list(global_files) if args.disable_global else [effective]
        for path in targets:
            before = originals[path]
            text = (before or b"").decode("utf-8")
            if args.disable_global and START not in text and END not in text:
                continue
            after = managed(text, None if args.disable_global else global_block(active_skill, args.agent)).encode("utf-8")
            if args.enable_global and budget is not None and len(after) > budget:
                raise ValueError(
                    f"Global instructions would be {len(after)} bytes, exceeding the declared "
                    f"instruction budget ({budget}). Shorten the global "
                    "file or configure a larger instruction budget in the host and pass the same "
                    "value via --instruction-budget. No enrollment was performed."
                )
            if after != (before or b""):
                updates.append((path, before, after))
                result["actions"].append({"action": "remove_global_block" if args.disable_global else "prepare_user_rules" if manual else "enroll_global", "path": str(path)})
        if not manual:
            result["effective_instructions"] = str(effective)
            result["activation"] = {"codex": "new_codex_run_or_session", "claude": "new_claude_code_session", "gemini": "memory_reload_and_skills_reload_or_new_session", "generic": "verify_that_the_host_loads_the_explicit_global_file"}[args.agent]
        result["instruction_budget"] = budget
        result["host_loading_verified"] = False
        if args.agent == "codex":
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
        with lock(effective.parent / ".project-memory-install.lock"):
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
    result["global_enabled"] = bool(args.enable_global and not manual and args.agent != "generic")
    if args.enable_global and args.agent == "generic":
        result["manual_action_required"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=["codex", "claude", "gemini", "cursor", "generic"], default="generic", help="Current host; unknown hosts stay generic and require explicit loading")
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--project", help="Exact existing project root for --scope project")
    parser.add_argument("--home", help="Home-like root for installation/testing; defaults to the user's home")
    parser.add_argument("--codex-home", help="Codex config root; otherwise CODEX_HOME or ~/.codex")
    parser.add_argument("--agent-home", help="Explicit native config directory (for Gemini this is the .gemini directory)")
    parser.add_argument("--global-instructions", help="Known global instruction file of a generic host; loading must be verified in that host")
    parser.add_argument("--rules-output", help="Output file for rules requiring manual host settings (Cursor/generic)")
    parser.add_argument("--enable-global", action="store_true", help="Enroll native global rules or prepare manual host User Rules")
    parser.add_argument("--global-only", action="store_true", help="Enroll this already managed Skill without copying it")
    parser.add_argument("--disable-global", action="store_true", help="Remove only this Skill's global instruction block")
    parser.add_argument("--instruction-budget", type=int, help="Actual host instruction budget; default 32768 only for Codex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.instruction_budget is not None and args.instruction_budget < 1:
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
