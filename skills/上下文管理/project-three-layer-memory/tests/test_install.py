"""Installer isolation, instruction preservation and enrollment tests."""
import importlib.util
import json
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install.py"
SPEC = importlib.util.spec_from_file_location("project_memory_install", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.codex = self.home / ".codex"

    def command(self, *options, success=True, env=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--home", str(self.home), *options],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def write_global(self, name="AGENTS.md", content="Existing working agreements.\n"):
        self.codex.mkdir(exist_ok=True)
        path = self.codex / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_dry_run_does_not_create_anything(self):
        result = self.command("--enable-global", "--dry-run")
        self.assertTrue(result["ok"])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_user_install_without_enrollment(self):
        self.command()
        self.assertTrue((self.home / ".agents/skills" / installer.NAME / "SKILL.md").is_file())
        self.assertFalse(self.codex.exists())

    def test_global_enrollment_preserves_original_and_backup(self):
        content = "# User agreements\r\n\r\nWork in the user's language.\r\n"
        target = self.write_global(content=content)
        # write_text on Unix preserves this explicit CRLF input.
        before = target.read_bytes()
        result = self.command("--enable-global")
        after = target.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual(after.count(installer.START.encode()), 1)
        self.assertEqual(Path(result["backups"][0]).read_bytes(), before)
        self.assertIn("new_codex_run_or_session", result["activation"])

    def test_repeat_install_and_enrollment_are_idempotent(self):
        self.command("--enable-global")
        path = self.codex / "AGENTS.md"
        original = path.read_bytes()
        result = self.command("--enable-global")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(result["actions"][0]["action"], "already_installed")

    def test_nonempty_override_receives_block(self):
        base = self.write_global(content="Base.\n")
        override = self.write_global("AGENTS.override.md", "Override.\n")
        self.command("--enable-global")
        self.assertEqual(base.read_text(), "Base.\n")
        self.assertIn(installer.START, override.read_text())

    def test_empty_override_uses_base(self):
        self.write_global("AGENTS.override.md", "\n")
        self.command("--enable-global")
        self.assertIn(installer.START, (self.codex / "AGENTS.md").read_text())

    def test_explicit_custom_codex_home(self):
        custom = self.root / "custom-config"
        self.command("--enable-global", "--codex-home", str(custom))
        self.assertTrue((custom / "AGENTS.md").is_file())
        self.assertFalse(self.codex.exists())

    def test_disable_keeps_other_rules_and_skill(self):
        target = self.write_global()
        self.command("--enable-global")
        with target.open("a") as handle:
            handle.write("\nA rule added later.\n")
        self.command("--disable-global")
        text = target.read_text()
        self.assertNotIn(installer.START, text)
        self.assertIn("Existing working agreements.", text)
        self.assertIn("A rule added later.", text)
        self.assertTrue((self.home / ".agents/skills" / installer.NAME).is_dir())
        original = target.read_bytes()
        self.command("--disable-global")
        self.assertEqual(target.read_bytes(), original)

    def test_disable_cleans_block_shadowed_by_later_override(self):
        target = self.write_global()
        self.command("--enable-global")
        override = self.write_global("AGENTS.override.md", "New override.\n")
        self.command("--disable-global")
        self.assertNotIn(installer.START, target.read_text())
        self.assertEqual(override.read_text(), "New override.\n")

    def test_malformed_global_markers_fail_before_install(self):
        target = self.write_global(content="Original\n" + installer.START)
        original = target.read_bytes()
        self.command("--enable-global", success=False)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.home / ".agents").exists())

    def test_existing_different_skill_never_overwritten(self):
        destination = self.home / ".agents/skills" / installer.NAME
        destination.mkdir(parents=True)
        keep = destination / "SKILL.md"
        keep.write_text("An existing custom skill.")
        self.command("--enable-global", success=False)
        self.assertEqual(keep.read_text(), "An existing custom skill.")
        self.assertFalse(self.codex.exists())

    def test_project_scope_stays_in_exact_folder(self):
        project = self.root / "课程 项目"
        project.mkdir()
        self.command("--scope", "project", "--project", str(project))
        self.assertTrue((project / ".agents/skills" / installer.NAME / "SKILL.md").is_file())
        self.assertFalse(self.codex.exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_project_scope_cannot_enable_global(self):
        project = self.root / "project"
        project.mkdir()
        self.command("--scope", "project", "--project", str(project), "--enable-global", success=False)
        self.assertEqual(list(project.iterdir()), [])

    def test_global_only_links_managed_source_without_copy(self):
        self.command("--global-only", "--enable-global")
        self.assertFalse((self.home / ".agents").exists())
        self.assertIn(str(installer.SKILL_DIR), (self.codex / "AGENTS.md").read_text())

    def test_global_only_requires_enable(self):
        self.command("--global-only", success=False)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_global_symlink_rejected_without_changing_target(self):
        outside = self.root / "outside.md"
        outside.write_text("Private unrelated instructions.")
        self.codex.mkdir()
        (self.codex / "AGENTS.md").symlink_to(outside)
        self.command("--enable-global", success=False)
        self.assertEqual(outside.read_text(), "Private unrelated instructions.")
        self.assertFalse((self.home / ".agents").exists())

    def test_skill_directory_symlink_escape_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.home / ".agents").symlink_to(outside, target_is_directory=True)
        self.command(success=False)
        self.assertEqual(list(outside.iterdir()), [])

    def test_global_compare_and_swap_rejects_concurrent_change(self):
        target = self.write_global()
        before = target.read_bytes()
        target.write_text("New state from another process.\n")
        with self.assertRaises(ValueError):
            installer.write_atomic(target, b"replacement", before)
        self.assertEqual(target.read_text(), "New state from another process.\n")

    def test_malformed_out_of_order_markers(self):
        with self.assertRaises(ValueError):
            installer.managed(installer.END + installer.START, "new")

    def test_budget_limit_fails_before_installing_or_modifying_rules(self):
        target = self.write_global(content="x" * 33000)
        before = target.read_bytes()
        self.command("--enable-global", success=False)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.home / ".agents").exists())

    def test_explicit_larger_codex_budget(self):
        target = self.write_global(content="x" * 33000)
        self.command("--enable-global", "--instruction-budget", "65536")
        self.assertIn(installer.START, target.read_text())

    def test_override_change_while_waiting_for_lock_rejects_enrollment(self):
        target = self.write_global(content="Original rules.\n")
        options = installer.argparse.Namespace(
            home=str(self.home), codex_home=None, disable_global=False,
            enable_global=True, global_only=True, scope="user", project=None,
            dry_run=False, instruction_budget=32768,
        )
        original_lock = installer.lock

        @contextmanager
        def racing_lock(path):
            self.write_global("AGENTS.override.md", "Concurrent overriding rules.\n")
            with original_lock(path):
                yield

        with mock.patch.object(installer, "lock", racing_lock):
            with self.assertRaisesRegex(ValueError, "Instructions changed"):
                installer.run(options)
        self.assertEqual(target.read_text(), "Original rules.\n")
        self.assertNotIn(installer.START, (self.codex / "AGENTS.override.md").read_text())

    def test_global_only_with_project_scope_rejected(self):
        project = self.root / "project"
        project.mkdir()
        self.command("--scope", "project", "--project", str(project), "--global-only", "--enable-global", success=False)


if __name__ == "__main__":
    unittest.main()
