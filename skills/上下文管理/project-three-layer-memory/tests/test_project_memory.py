"""Behavioral tests for project-local persistence, isolation and safe updates."""
import hashlib
from contextlib import contextmanager, redirect_stdout
import io
from unittest import mock
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'project_memory.py'
spec = importlib.util.spec_from_file_location('project_memory', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProjectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='project-memory-tests-')
        self.base = Path(self.tmp.name)
        self.project = self.base / '训练营 项目甲'
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, project=None, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), args[0], '--project', str(project or self.project), *args[1:]], text=True, capture_output=True)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f'Expected JSON: {result.stdout!r} {result.stderr!r}')
        if success:
            self.assertEqual(result.returncode, 0, payload)
            self.assertTrue(payload['ok'])
        else:
            self.assertNotEqual(result.returncode, 0, payload)
        return payload

    def init(self, **kwargs):
        return self.run_cli('init', **kwargs)

    def test_empty_non_git_project_and_audit_distinguish_templates(self):
        result = self.init()
        self.assertEqual(result['content_status'], 'templates_only')
        self.assertFalse((self.project / '.git').exists())
        self.assertTrue((self.project / '.project-memory/history').is_dir())
        self.assertTrue(self.run_cli('audit')['initialized'])
        self.assertEqual(self.run_cli('audit')['content_status'], 'templates_only')
        self.assertFalse((self.project / 'CLAUDE.md').exists())

    def test_dry_run_has_no_side_effects(self):
        result = self.run_cli('init', '--dry-run')
        self.assertTrue(result['dry_run'])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_existing_rules_survive_and_init_is_idempotent(self):
        original = '# Existing rules\n\nKeep this exactly: café 中文。\n'
        (self.project / 'AGENTS.md').write_text(original, encoding='utf-8')
        self.init()
        first = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        self.init()
        second = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        self.assertEqual(first, second)
        self.assertTrue((self.project / 'AGENTS.md').read_text().startswith(original))
        self.assertEqual((self.project / 'AGENTS.md').read_text().count(module.START_MARKER), 1)

    def test_effective_override_is_patched_without_touching_base(self):
        (self.project / 'AGENTS.md').write_text('base rules\n')
        (self.project / 'AGENTS.override.md').write_text('override rules\n')
        self.init()
        self.assertEqual((self.project / 'AGENTS.md').read_text(), 'base rules\n')
        self.assertTrue((self.project / 'AGENTS.override.md').read_text().startswith('override rules\n'))
        self.assertEqual(self.run_cli('audit')['instruction_file'], 'AGENTS.override.md')

    def test_empty_override_falls_back_to_agents(self):
        (self.project / 'AGENTS.override.md').write_text('  \n')
        self.init()
        self.assertEqual(self.run_cli('audit')['instruction_file'], 'AGENTS.md')

    def test_existing_context_state_can_be_mapped_without_copying(self):
        context = '# 课程项目\n目标：制作课程，验收：完成一场试讲。\n'
        state = '# 当前进展\n已完成：大纲。未完成：试讲。\n'
        (self.project / 'CONTEXT.md').write_text(context)
        (self.project / 'PROGRESS.md').write_text(state)
        plan = self.run_cli('init', '--dry-run')
        self.assertEqual(plan['reuse_candidates'], ['CONTEXT.md', 'PROGRESS.md'])
        self.run_cli('init', '--context-file', 'CONTEXT.md', '--state-file', 'PROGRESS.md')
        self.assertEqual((self.project / 'CONTEXT.md').read_text(), context)
        self.assertEqual((self.project / 'PROGRESS.md').read_text(), state)
        self.assertFalse((self.project / '.project-memory/PROJECT.md').exists())
        self.assertFalse((self.project / '.project-memory/STATE.md').exists())
        self.init()
        resumed = self.run_cli('resume')
        self.assertEqual(resumed['documents'][0]['path'], 'CONTEXT.md')
        self.assertEqual(resumed['documents'][1]['path'], 'PROGRESS.md')

    def test_invalid_mapping_is_rejected_before_any_writes(self):
        self.run_cli('init', '--context-file', '../outside.md', success=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.run_cli('init', '--context-file', 'missing.md', success=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_duplicate_role_mapping_rejected(self):
        (self.project / 'existing.md').write_text('existing')
        self.run_cli('init', '--context-file', 'existing.md', '--state-file', 'existing.md', success=False)
        self.assertFalse((self.project / '.project-memory').exists())

    def test_symlink_memory_directory_does_not_write_outside(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.project / '.project-memory').symlink_to(outside, target_is_directory=True)
        self.run_cli('init', success=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.project / 'AGENTS.md').exists())

    def test_symlink_rule_is_rejected_before_writes(self):
        outside = self.base / 'outside.md'
        outside.write_text('do not change')
        (self.project / 'AGENTS.md').symlink_to(outside)
        self.run_cli('init', success=False)
        self.assertEqual(outside.read_text(), 'do not change')
        self.assertFalse((self.project / '.project-memory').exists())

    def test_symlink_parent_of_mapping_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'context.md').write_text('outside')
        (self.project / 'docs').symlink_to(outside, target_is_directory=True)
        self.run_cli('init', '--context-file', 'docs/context.md', success=False)
        self.assertFalse((self.project / '.project-memory').exists())

    def test_malformed_markers_do_not_pollute_project(self):
        (self.project / 'AGENTS.md').write_text(module.START_MARKER + '\nincomplete')
        self.run_cli('init', success=False)
        self.assertFalse((self.project / '.project-memory').exists())

    def test_secret_rejected_and_not_echoed(self):
        self.init()
        secret = 'password=super-secret-example-0123'
        result = self.run_cli('record', '--layer', 'history', '--content', secret, '--source', 'task', '--status', 'observed', success=False)
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(list((self.project / '.project-memory/history').iterdir()), [])

    def test_history_record_deduplicates_and_preserves_multiline(self):
        self.init()
        content = '第一次试讲已完成。\n- 到场 8 人。\n- 下次修正练习说明。'
        args = ('record', '--layer', 'history', '--content', content, '--source', 'meeting/notes.md:12', '--status', 'observed')
        result = self.run_cli(*args)
        duplicate = self.run_cli(*args)
        self.assertEqual(duplicate['status'], 'duplicate_skipped')
        saved = (self.project / result['path']).read_text()
        self.assertIn(content, saved)
        self.assertIn('meeting/notes.md:12', saved)
        self.assertIn('状态：observed', saved)

    def test_separate_process_resume_sees_sourced_context(self):
        self.init()
        self.run_cli('record', '--layer', 'project', '--content', '目标：让学员交付一份可复现报告。', '--source', 'user requirement', '--status', 'confirmed')
        resumed = self.run_cli('resume')
        project_doc = resumed['documents'][0]
        self.assertIn('可复现报告', project_doc['content'])
        self.assertIn('user requirement', project_doc['content'])
        self.assertEqual(project_doc['sha256'], hashlib.sha256((self.project / project_doc['path']).read_bytes()).hexdigest())
        self.assertFalse(resumed['history_loaded'])

    def test_resume_budget_is_explicitly_truncated(self):
        self.init()
        resumed = self.run_cli('resume', '--max-chars', '200')
        self.assertLessEqual(sum(len(d['content']) for d in resumed['documents']), 200)
        self.assertTrue(any(d['truncated'] for d in resumed['documents']))

    def test_project_a_b_isolation(self):
        second = self.base / '项目乙'
        second.mkdir()
        self.init()
        self.init(project=second)
        self.run_cli('record', '--layer', 'history', '--content', '只有甲项目知道的橙色实验', '--source', 'task-A', '--status', 'observed')
        self.assertTrue(self.run_cli('recall', '--query', '橙色实验')['matches'])
        self.assertEqual(self.run_cli('recall', '--query', '橙色实验', project=second)['matches'], [])

    def test_checkpoint_hash_protects_concurrent_state_and_archives_previous(self):
        self.init()
        resumed = self.run_cli('resume')
        content = self.base / 'checkpoint.md'
        content.write_text('# 当前交接\n\n完成：大纲。\n未完成：试讲。\n下一步：邀请试讲者。\n')
        args = ('checkpoint', '--content-file', str(content), '--source', 'run-1 verification', '--expected-sha256', resumed['state_sha256'])
        result = self.run_cli(*args)
        archive = (self.project / result['previous_state_archive']).read_text()
        self.assertIn('尚未记录；初始化不等于项目完成', archive)
        saved = (self.project / '.project-memory/STATE.md').read_bytes()
        stale = self.run_cli(*args, success=False)
        self.assertIn('State changed', stale['error'])
        self.assertEqual((self.project / '.project-memory/STATE.md').read_bytes(), saved)
        self.assertEqual(len(list((self.project / '.project-memory/history').iterdir())), 1)
        self.assertIn('邀请试讲者', self.run_cli('resume')['documents'][1]['content'])

    def test_checkpoint_dry_run_does_not_change_state(self):
        self.init()
        resumed = self.run_cli('resume')
        self.run_cli('checkpoint', '--content', '下一步：完成试讲', '--source', 'user', '--expected-sha256', resumed['state_sha256'], '--dry-run')
        self.assertEqual(self.run_cli('resume')['state_sha256'], resumed['state_sha256'])
        self.assertEqual(list((self.project / '.project-memory/history').iterdir()), [])

    def test_opt_out_prevents_initialization_and_future_writes(self):
        (self.project / '.project-memory-disabled').write_text('disabled')
        self.run_cli('init', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertTrue(self.run_cli('audit', success=False)['disabled'])
        (self.project / '.project-memory-disabled').unlink()
        self.init()
        (self.project / '.project-memory-disabled').write_text('disabled')
        self.run_cli('record', '--layer', 'history', '--content', 'do not write', '--source', 'user', '--status', 'confirmed', success=False)

    def test_existing_lock_prevents_writes(self):
        self.init()
        (self.project / '.project-memory/.write-lock').write_text('other writer')
        self.run_cli('record', '--layer', 'history', '--content', 'blocked', '--source', 'user', '--status', 'confirmed', success=False)
        self.assertEqual((self.project / '.project-memory/.write-lock').read_text(), 'other writer')

    def test_audit_reports_missing_state_and_redacts_suspected_secret(self):
        self.init()
        (self.project / '.project-memory/STATE.md').unlink()
        result = self.run_cli('audit', success=False)
        self.assertIn('.project-memory/STATE.md', result['missing'])
        self.init()
        target = self.project / '.project-memory/PROJECT.md'
        target.write_text(target.read_text() + '\npassword=do-not-print-12345\n')
        result = self.run_cli('audit', success=False)
        self.assertTrue(result['suspected_secrets'])
        self.assertNotIn('do-not-print', json.dumps(result))
        self.assertNotIn('do-not-print', self.run_cli('resume')['documents'][0]['content'])

    def test_existing_rule_newline_bytes_survive(self):
        original = b'# Rules\r\n\r\nKeep Windows newlines.\r\n'
        (self.project / 'AGENTS.md').write_bytes(original)
        self.init()
        self.assertTrue((self.project / 'AGENTS.md').read_bytes().startswith(original))
        first = (self.project / 'AGENTS.md').read_bytes()
        self.init()
        self.assertEqual((self.project / 'AGENTS.md').read_bytes(), first)

    def test_checkpoint_rejects_secret_in_previous_state_without_archiving(self):
        self.init()
        (self.project / '.project-memory/STATE.md').write_text('password=must-not-copy-12345')
        resumed = self.run_cli('resume')
        self.run_cli('checkpoint', '--content', 'Safe replacement', '--source', 'user', '--expected-sha256', resumed['state_sha256'], success=False)
        self.assertEqual(list((self.project / '.project-memory/history').iterdir()), [])

    def test_audit_detects_missing_history_directory(self):
        self.init()
        (self.project / '.project-memory/history').rmdir()
        result = self.run_cli('audit', success=False)
        self.assertIn('.project-memory/history', result['missing'])

    def test_two_checkpoint_writers_do_not_overwrite_each_other(self):
        self.init()
        resumed = self.run_cli('resume')
        command = [sys.executable, str(SCRIPT), 'checkpoint', '--project', str(self.project), '--source', 'concurrent-test', '--expected-sha256', resumed['state_sha256']]
        first = subprocess.Popen(command + ['--content', 'First writer handoff'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command + ['--content', 'Second writer handoff'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first_result = first.communicate(timeout=10)
        second_result = second.communicate(timeout=10)
        self.assertEqual(sorted([first.returncode, second.returncode]), [0, 1], (first_result, second_result))
        state = (self.project / '.project-memory/STATE.md').read_text()
        self.assertNotEqual('First writer handoff' in state, 'Second writer handoff' in state)
        self.assertEqual(len(list((self.project / '.project-memory/history').iterdir())), 1)

    def test_init_reloads_mapping_after_acquiring_lock(self):
        self.init()
        (self.project / 'CONTEXT.md').write_text('# Existing authoritative project context\n')
        @contextmanager
        def competing_initializer(project):
            config_path = project / '.project-memory/paths.json'
            config = json.loads(config_path.read_text())
            config['files']['project'] = 'CONTEXT.md'
            config_path.write_text(json.dumps(config))
            yield
        args = module.build_parser().parse_args(['init', '--project', str(self.project)])
        with mock.patch.object(module, 'project_lock', competing_initializer), redirect_stdout(io.StringIO()):
            self.assertEqual(module.cmd_init(args), 0)
        config = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertEqual(config['files']['project'], 'CONTEXT.md')
        self.assertIn('`CONTEXT.md`', (self.project / 'AGENTS.md').read_text())

    @unittest.skipUnless(shutil.which('git'), 'Git is used only for this clone simulation')
    def test_tracked_project_copy_keeps_mapping_despite_config_json_ignore(self):
        (self.project / '.gitignore').write_text('config.json\n')
        (self.project / 'CONTEXT.md').write_text('# Authority\n目标：复制项目后继续课程设计。\n')
        (self.project / 'PROGRESS.md').write_text('# Handoff\n下一步：完成练习题。\n')
        self.run_cli('init', '--context-file', 'CONTEXT.md', '--state-file', 'PROGRESS.md')
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True, capture_output=True)
        ignored = subprocess.run(['git', '-C', str(self.project), 'check-ignore', '.project-memory/paths.json'], capture_output=True)
        self.assertEqual(ignored.returncode, 1)
        subprocess.run(['git', '-C', str(self.project), 'add', '.'], check=True, capture_output=True)
        tracked = subprocess.check_output(['git', '-C', str(self.project), 'ls-files', '-z']).decode().split('\x00')
        self.assertIn('.project-memory/paths.json', tracked)
        copied = self.base / '另一台电脑上的课程项目'
        copied.mkdir()
        for relative in filter(None, tracked):
            target = copied / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.project / relative, target)
        # Git does not preserve empty directories. Resume still works before the
        # first record recreates the history directory in this copied project.
        resumed = self.run_cli('resume', project=copied)
        self.assertEqual(resumed['documents'][0]['path'], 'CONTEXT.md')
        self.assertEqual(resumed['documents'][1]['path'], 'PROGRESS.md')
        self.assertIn('完成练习题', resumed['documents'][1]['content'])
        self.run_cli('record', '--layer', 'history', '--content', '复制后的项目已继续练习题设计。', '--source', 'new-session', '--status', 'observed', project=copied)
        self.assertTrue(self.run_cli('audit', project=copied)['initialized'])

    def test_persisted_paths_are_portable_and_windows_style_input_is_normalized(self):
        docs = self.project / 'docs'
        docs.mkdir()
        (docs / 'CONTEXT.md').write_text('# Project context\n'.replace('\\n', '\n'))
        self.run_cli('init', '--context-file', r'docs\CONTEXT.md')
        config = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertEqual(config['files']['project'], 'docs/CONTEXT.md')
        self.assertEqual(config['history_dir'], '.project-memory/history')
        self.assertTrue(all('\\' not in path for path in config['files'].values()))
        # A legacy Windows-produced relative mapping is accepted after copying
        # files onto another OS; future writes serialize the same POSIX form.
        config['files']['project'] = r'docs\CONTEXT.md'
        config['history_dir'] = r'.project-memory\history'
        (self.project / '.project-memory/paths.json').write_text(json.dumps(config))
        resumed = self.run_cli('resume')
        self.assertEqual(resumed['documents'][0]['path'], 'docs/CONTEXT.md')
        self.assertEqual(resumed['history_path'], '.project-memory/history')
        self.init()
        normalized = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertEqual(normalized['files']['project'], 'docs/CONTEXT.md')
        self.assertEqual(normalized['history_dir'], '.project-memory/history')

    def test_windows_drive_and_unc_paths_are_rejected_as_mappings(self):
        for path in (r'C:\outside\context.md', r'\\server\share\context.md', r'..\outside.md'):
            self.run_cli('init', '--context-file', path, success=False)
        self.assertFalse((self.project / '.project-memory').exists())

    def test_codex_and_generic_do_not_create_other_native_entries(self):
        self.run_cli('init', '--agent', 'codex')
        self.run_cli('init', '--agent', 'generic')
        self.assertFalse((self.project / 'CLAUDE.md').exists())
        self.assertFalse((self.project / 'GEMINI.md').exists())
        config = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertNotIn('bridges', config)
        self.assertEqual(self.run_cli('audit')['bridges'], [])

    def test_claude_bridge_initialization_is_registered_and_audited(self):
        result = self.run_cli('init', '--agent', 'claude')
        self.assertEqual(result['mapping']['bridges'], ['claude'])
        self.assertEqual(list(module.active_imports((self.project / 'CLAUDE.md').read_text())), ['AGENTS.md'])
        self.assertFalse((self.project / 'GEMINI.md').exists())
        report = self.run_cli('audit')
        self.assertTrue(report['bridges_ok'])
        self.assertEqual(report['bridges'][0]['agent'], 'claude')
        self.assertEqual(report['bridges'][0]['target'], 'AGENTS.md')

    def test_gemini_bridge_initialization_preserves_native_rules_and_newlines(self):
        original = '# Gemini rules\r\n\r\nKeep the original guidance.\r\n'.encode()
        (self.project / 'GEMINI.md').write_bytes(original)
        self.run_cli('init', '--agent', 'gemini')
        native = self.project / 'GEMINI.md'
        self.assertTrue(native.read_bytes().startswith(original))
        first = native.read_bytes()
        self.run_cli('init', '--agent', 'gemini')
        self.assertEqual(native.read_bytes(), first)
        self.assertEqual(list(module.active_imports(native.read_text())), ['AGENTS.md'])
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_native_bridge_dry_run_has_no_side_effects(self):
        plan = self.run_cli('init', '--agent', 'claude', '--dry-run')
        self.assertTrue(any(item['path'] == 'CLAUDE.md' for item in plan['actions']))
        self.assertEqual(list(self.project.iterdir()), [])

    def test_two_native_hosts_share_memory_and_survive_default_reinitialization(self):
        self.run_cli('init', '--agent', 'claude')
        first_claude = (self.project / 'CLAUDE.md').read_bytes()
        self.run_cli('init', '--agent', 'gemini')
        self.assertEqual((self.project / 'CLAUDE.md').read_bytes(), first_claude)
        self.init()
        config = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertEqual(config['bridges'], ['claude', 'gemini'])
        self.assertEqual(len(self.run_cli('audit')['bridges']), 2)
        self.assertEqual((self.project / 'CLAUDE.md').read_bytes(), first_claude)

    def test_all_registered_native_imports_follow_effective_override_changes(self):
        self.run_cli('init', '--agent', 'claude')
        self.run_cli('init', '--agent', 'gemini')
        (self.project / 'AGENTS.override.md').write_text('# Temporary project override\n')
        self.init()
        for filename in ('CLAUDE.md', 'GEMINI.md'):
            self.assertEqual(list(module.active_imports((self.project / filename).read_text())), ['AGENTS.override.md'])
        self.assertTrue(self.run_cli('audit')['bridges_ok'])
        (self.project / 'AGENTS.override.md').unlink()
        self.run_cli('init', '--agent', 'codex')
        for filename in ('CLAUDE.md', 'GEMINI.md'):
            self.assertEqual(list(module.active_imports((self.project / filename).read_text())), ['AGENTS.md'])

    def test_existing_independent_native_import_is_reused_without_changing_bytes(self):
        original = b'# Native rules\r\n\r\n@./AGENTS.md\r\n'
        (self.project / 'CLAUDE.md').write_bytes(original)
        self.run_cli('init', '--agent', 'claude')
        self.assertEqual((self.project / 'CLAUDE.md').read_bytes(), original)
        self.run_cli('init', '--agent', 'claude')
        self.assertEqual((self.project / 'CLAUDE.md').read_bytes(), original)
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_example_native_import_is_not_mistaken_for_an_active_import(self):
        original = '# Examples\n```md\n<!-- example comment\n@AGENTS.md\n```\n'
        (self.project / 'GEMINI.md').write_text(original)
        self.run_cli('init', '--agent', 'gemini')
        text = (self.project / 'GEMINI.md').read_text()
        self.assertTrue(text.startswith(original))
        self.assertEqual(list(module.active_imports(text)), ['AGENTS.md'])
        self.assertIn(module.bridge_markers('gemini')[0], text)

    def test_malformed_native_bridge_markers_reject_before_project_writes(self):
        (self.project / 'CLAUDE.md').write_text('# Existing\n' + module.bridge_markers('claude')[0])
        self.run_cli('init', '--agent', 'claude', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertFalse((self.project / 'AGENTS.md').exists())

    def test_native_symlink_rejects_before_project_writes(self):
        outside = self.base / 'outside-native.md'
        outside.write_text('external rules')
        try:
            (self.project / 'GEMINI.md').symlink_to(outside)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        self.run_cli('init', '--agent', 'gemini', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertFalse((self.project / 'AGENTS.md').exists())
        self.assertEqual(outside.read_text(), 'external rules')

    def test_unclosed_native_examples_reject_before_project_writes(self):
        for name, text, agent in (('CLAUDE.md', '# Examples\n```md\n', 'claude'), ('GEMINI.md', '# Comments\n<!-- unfinished', 'gemini')):
            with self.subTest(agent=agent):
                (self.project / name).write_text(text)
                self.run_cli('init', '--agent', agent, success=False)
                self.assertFalse((self.project / '.project-memory').exists())
                self.assertFalse((self.project / 'AGENTS.md').exists())
                self.assertEqual((self.project / name).read_text(), text)

    def test_direct_native_import_cycle_is_rejected_without_pollution(self):
        (self.project / 'AGENTS.md').write_text('# Shared rules\n@CLAUDE.md\n')
        self.run_cli('init', '--agent', 'claude', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertFalse((self.project / 'CLAUDE.md').exists())
        self.assertEqual((self.project / 'AGENTS.md').read_text(), '# Shared rules\n@CLAUDE.md\n')

    def test_audit_reports_missing_registered_native_bridge(self):
        self.run_cli('init', '--agent', 'gemini')
        (self.project / 'GEMINI.md').unlink()
        report = self.run_cli('audit', success=False)
        self.assertFalse(report['bridges_ok'])
        self.assertEqual(report['bridges'][0]['error'], 'native_entry_missing')
        self.init()
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_audit_reports_stale_managed_import_despite_an_independent_new_import(self):
        self.run_cli('init', '--agent', 'claude')
        (self.project / 'AGENTS.override.md').write_text('# Override\n')
        path = self.project / 'CLAUDE.md'
        path.write_text(path.read_text() + '\n@AGENTS.override.md\n')
        report = self.run_cli('audit', success=False)
        self.assertEqual(report['bridges'][0]['error'], 'managed_native_import_outdated')
        self.init()
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_legacy_config_without_bridge_list_remains_usable(self):
        self.init()
        config = json.loads((self.project / '.project-memory/paths.json').read_text())
        self.assertNotIn('bridges', config)
        self.assertTrue(self.run_cli('resume')['ok'])
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_indented_code_import_is_not_reused_as_an_active_import(self):
        (self.project / 'CLAUDE.md').write_text('# Example\n\n    @AGENTS.md\n')
        self.run_cli('init', '--agent', 'claude')
        text = (self.project / 'CLAUDE.md').read_text()
        self.assertEqual(list(module.active_imports(text)), ['AGENTS.md'])
        self.assertIn(module.bridge_markers('claude')[0], text)

    def test_hidden_claude_context_and_other_host_entry_are_untouched(self):
        hidden = self.project / '.claude'
        hidden.mkdir()
        (hidden / 'CLAUDE.md').write_text('Keep hidden project context exactly.\n')
        (self.project / 'GEMINI.md').write_text('Keep Gemini context exactly.\n')
        self.run_cli('init', '--agent', 'claude')
        self.assertTrue((self.project / 'CLAUDE.md').is_file())
        self.assertEqual((hidden / 'CLAUDE.md').read_text(), 'Keep hidden project context exactly.\n')
        self.assertEqual((self.project / 'GEMINI.md').read_text(), 'Keep Gemini context exactly.\n')

    def test_inline_native_import_cycle_is_rejected_before_any_write(self):
        for agent, native in (('claude', 'CLAUDE.md'), ('gemini', 'GEMINI.md')):
            with self.subTest(agent=agent):
                original = f'Read @{native} for additional user requirements.\n'
                (self.project / 'AGENTS.md').write_text(original)
                self.run_cli('init', '--agent', agent, success=False)
                self.assertFalse((self.project / '.project-memory').exists())
                self.assertFalse((self.project / native).exists())
                self.assertEqual((self.project / 'AGENTS.md').read_text(), original)

    def test_audit_detects_preexisting_inline_native_import_cycle(self):
        self.run_cli('init', '--agent', 'claude')
        path = self.project / 'AGENTS.md'
        path.write_text(path.read_text() + '\nRead @CLAUDE.md for additional user requirements.\n')
        report = self.run_cli('audit', success=False)
        self.assertFalse(report['bridges_ok'])
        self.assertEqual(report['bridges'][0]['error'], 'direct_import_cycle')

    def test_inline_native_import_detection_excludes_examples_comments_and_urls(self):
        text = ('Use `@CLAUDE.md` as an example.\n'
                'Use ``@CLAUDE.md`` as another example.\n'
                '<!-- Read @CLAUDE.md only in this hidden comment. -->\n'
                '```md\nRead @CLAUDE.md in a fenced example.\n```\n'
                '    Read @CLAUDE.md in an indented code example.\n'
                'See https://example.test/@CLAUDE.md and https://example.test/?name=@GEMINI.md .\n'
                'Email helper@CLAUDE.md or use mailto:@GEMINI.md .\n'
                'See [Claude](CLAUDE.md) and the backup @CLAUDE.md.backup.\n'
                'Do not mistake @CLAUDE.md/subpath for a root import.\n')
        self.assertEqual(module.potential_native_imports(text, self.project), set())
        (self.project / 'AGENTS.md').write_text(text)
        self.run_cli('init', '--agent', 'claude')
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_inline_native_import_boundaries_include_relative_names_and_punctuation(self):
        text = 'Read (@./CLAUDE.md), and reference:@././GEMINI.md.\n'
        self.assertEqual(module.potential_native_imports(text, self.project), {'CLAUDE.md', 'GEMINI.md'})
        self.assertEqual(module.potential_native_imports('Read @claude.md for case-insensitive file systems.', self.project), {'CLAUDE.md'})

    def test_inline_existing_forward_import_does_not_relax_standalone_reuse(self):
        original = 'Read @AGENTS.md for project requirements.\n'
        (self.project / 'CLAUDE.md').write_text(original)
        self.run_cli('init', '--agent', 'claude')
        text = (self.project / 'CLAUDE.md').read_text()
        self.assertTrue(text.startswith(original))
        self.assertIn(module.bridge_markers('claude')[0], text)
        self.assertEqual(list(module.active_imports(text)), ['AGENTS.md'])

    def test_absolute_native_import_cycle_is_rejected_before_writes(self):
        project = self.base / 'absolute-project'
        project.mkdir()
        native = project / 'CLAUDE.md'
        original = f'Read @{native.as_posix()} for requirements.\n'
        (project / 'AGENTS.md').write_text(original)
        self.run_cli('init', '--agent', 'claude', project=project, success=False)
        self.assertFalse((project / '.project-memory').exists())
        self.assertFalse(native.exists())
        self.assertEqual((project / 'AGENTS.md').read_text(), original)

    def test_absolute_escaped_space_native_import_cycle_is_rejected(self):
        alias = (self.project / 'CLAUDE.md').as_posix().replace(' ', '\\ ')
        (self.project / 'AGENTS.md').write_text(f'Read @{alias} for requirements.\n')
        self.run_cli('init', '--agent', 'claude', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertFalse((self.project / 'CLAUDE.md').exists())

    def test_normalized_relative_native_aliases_are_rejected_without_writes(self):
        aliases = ('./scratch/../CLAUDE.md',
                   ('../' + self.project.name + '/CLAUDE.md').replace(' ', '\\ '),
                   '.\\scratch\\..\\CLAUDE.md')
        for alias in aliases:
            with self.subTest(alias=alias):
                original = f'Read @{alias} for requirements.\n'
                (self.project / 'AGENTS.md').write_text(original)
                self.run_cli('init', '--agent', 'claude', success=False)
                self.assertFalse((self.project / '.project-memory').exists())
                self.assertFalse((self.project / 'CLAUDE.md').exists())
                self.assertEqual((self.project / 'AGENTS.md').read_text(), original)

    def test_audit_detects_absolute_and_normalized_native_import_cycles(self):
        self.run_cli('init', '--agent', 'claude')
        path = self.project / 'AGENTS.md'
        original = path.read_text()
        aliases = ((self.project / 'CLAUDE.md').as_posix().replace(' ', '\\ '), './unused/../CLAUDE.md')
        for alias in aliases:
            with self.subTest(alias=alias):
                path.write_text(original + f'\nRead @{alias} for requirements.\n')
                report = self.run_cli('audit', success=False)
                self.assertEqual(report['bridges'][0]['error'], 'direct_import_cycle')

    def test_same_project_symlink_alias_is_detected_without_following_document_content(self):
        alias = self.base / 'project-alias'
        try:
            alias.symlink_to(self.project, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        (self.project / 'AGENTS.md').write_text('Read @../project-alias/CLAUDE.md for requirements.\n')
        self.run_cli('init', '--agent', 'claude', success=False)
        self.assertFalse((self.project / '.project-memory').exists())
        self.assertFalse((self.project / 'CLAUDE.md').exists())

    def test_quoted_native_path_examples_are_not_interpreted_as_imports(self):
        absolute = (self.project / 'CLAUDE.md').as_posix()
        examples = (f'Read "@{absolute}" as an example.\n'
                    f'Example: @"{absolute}"\n'
                    "Read '@CLAUDE.md' as another example.\n"
                    'Use ``@./CLAUDE.md`` and `@./unused/../CLAUDE.md` as examples.\n')
        self.assertEqual(module.potential_native_imports(examples, self.project), set())
        (self.project / 'AGENTS.md').write_text(examples)
        self.run_cli('init', '--agent', 'claude')
        self.assertTrue(self.run_cli('audit')['bridges_ok'])

    def test_native_import_resolution_uses_rule_location_and_keeps_other_projects_distinct(self):
        subdir = self.project / 'instructions'
        subdir.mkdir()
        self.assertEqual(module.potential_native_imports('Read @../CLAUDE.md for rules.', self.project, subdir), {'CLAUDE.md'})
        outside = self.base / 'another-project'
        outside.mkdir()
        self.assertEqual(module.potential_native_imports(f'Read @{outside.as_posix()}/CLAUDE.md for rules.', self.project), set())
        self.assertEqual(module.potential_native_imports('Read @./CLAUDE.md.backup and @./CLAUDE.md/subpath.', self.project), set())

    def test_broad_root_is_refused(self):
        self.run_cli('init', project=Path.home(), success=False)


if __name__ == '__main__':
    unittest.main()
