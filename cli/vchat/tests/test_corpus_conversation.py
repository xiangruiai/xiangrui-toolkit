"""Isolated corpus transport checks: no live DB, key, CLI process or snapshot."""
import argparse
import ast
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

CLI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLI_ROOT))
from vchat_core import corpus

ROOM = '10000000001@chatroom'
OTHER = 'synthetic-other@chatroom'
TABLE = 'Msg_' + hashlib.md5(ROOM.encode()).hexdigest()
OTHER_TABLE = 'Msg_' + hashlib.md5(OTHER.encode()).hexdigest()
BASE_TIME = 1700000000


class CorpusConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vchat-corpus-conversation-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'generation' / 'decrypted'
        (self.root / 'message').mkdir(parents=True)
        (self.root / 'contact').mkdir()
        for shard in (0, 1):
            with sqlite3.connect(self.root / 'message' / f'message_{shard}.db') as db:
                db.execute('CREATE TABLE Name2Id (user_name TEXT)')
                db.executemany('INSERT INTO Name2Id VALUES (?)', [('wxid_self',), ('wxid_member',)])
                for table in (TABLE, OTHER_TABLE):
                    db.execute(f'CREATE TABLE "{table}" (local_id INTEGER PRIMARY KEY,server_id INTEGER,real_sender_id INTEGER,local_type INTEGER,create_time INTEGER,message_content TEXT)')
                target = [(1, 9223372036854775807, 1, 1, BASE_TIME, 'target first'),
                          (2, 0, 2, 1, BASE_TIME + 1, 'target local only'),
                          (3, 903, 2, 1, BASE_TIME + 2, 'target third')] if shard == 0 else [
                          (1, 9223372036854775807, 1, 1, BASE_TIME + 2, 'target duplicate server'),
                          (2, 0, 2, 1, BASE_TIME + 3, 'target second shard')]
                db.executemany(f'INSERT INTO "{TABLE}" VALUES (?,?,?,?,?,?)', target)
                others = [(1, 990 + shard, 2, 1, BASE_TIME, 'OTHER_CHAT_BODY_CANARY')]
                if shard == 0:
                    others.append((2, 999, 2, 1, BASE_TIME + 1, 'OTHER_CHAT_BODY_CANARY_2'))
                db.executemany(f'INSERT INTO "{OTHER_TABLE}" VALUES (?,?,?,?,?,?)', others)
        with sqlite3.connect(self.root / 'contact' / 'contact.db') as db:
            db.execute('CREATE TABLE contact (username TEXT, nick_name TEXT, remark TEXT)')
            db.executemany('INSERT INTO contact VALUES (?,?,?)', [
                (ROOM, '合成指定群', ''), (OTHER, '合成其他群', ''),
                ('wxid_self', '合成本人', ''), ('wxid_member', '合成成员', '')])
        self.binding = {'snapshot_id': 'synthetic-generation', 'created_at': '2026-10-08T00:00:00Z',
                        'source_identity': {'id': 'local-source:synthetic', 'kind': 'synthetic'},
                        'coverage': {'complete': True},
                        'outputs': {name: {} for name in ['message/message_0.db', 'message/message_1.db', 'contact/contact.db']}}
        self.binding_patch = patch.object(corpus, '_binding', return_value=(self.binding, self.root))
        self.binding_patch.start()
        self.addCleanup(self.binding_patch.stop)

    @contextlib.contextmanager
    def target_reads_only(self):
        original = corpus._connection
        attempted = []

        @contextlib.contextmanager
        def guarded(*args, **kwargs):
            with original(*args, **kwargs) as db:
                def authorize(action, table, _column, _database, _trigger):
                    if action == sqlite3.SQLITE_READ and str(table).lower().startswith('msg_') and table.lower() != TABLE.lower():
                        attempted.append(table)
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                db.set_authorizer(authorize)
                yield db
        with patch.object(corpus, '_connection', guarded):
            yield attempted
        self.assertEqual(attempted, [], 'another message table was read, even for COUNT')

    def test_target_stats_and_stream_do_not_read_other_message_tables(self):
        with self.target_reads_only():
            result = corpus.stats('synthetic', conversation=ROOM)
            self.assertEqual(result['source_total'], 5)
            self.assertEqual(result['source_tables'], 2)
            self.assertEqual(result['conversation_filter'], ROOM)
            self.assertEqual(result['all_source_total_scope'], 'selected-conversation')
            self.assertFalse(result['coverage']['all_snapshot_message_shards_counted'])
            self.assertTrue(result['coverage']['selected_conversation_all_shards_counted'])
            self.assertFalse(result['coverage']['other_conversations_scanned'])
            pages = list(corpus.iter_export('synthetic', conversation=ROOM, limit=2))
            self.assertEqual([page['rows_returned'] for page in pages], [2, 2, 1])
            self.assertTrue(pages[-1]['complete'])
            self.assertIsNone(pages[-1]['next_cursor'])
            items = [item for page in pages for item in page['items']]
            self.assertEqual({item['conversation_id'] for item in items}, {ROOM})
            self.assertNotIn('OTHER_CHAT_BODY_CANARY', json.dumps(pages))
            self.assertEqual(len({item['record_id'] for item in items}), 5)

    def test_cursor_scope_mismatch_rejected_before_any_inventory_read(self):
        page = corpus.export('synthetic', conversation=ROOM, limit=1)
        cursor = page['next_cursor']
        decoded = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        self.assertEqual(decoded['conversation_filter'], ROOM)
        with patch.object(corpus, '_inventory', side_effect=AssertionError('scope mismatch reached inventory')):
            for conversation in (None, OTHER):
                with self.assertRaisesRegex(RuntimeError, '会话过滤不匹配'):
                    corpus.export('synthetic', cursor=cursor, conversation=conversation)
        with self.target_reads_only():
            resumed = corpus.export('synthetic', conversation=ROOM, cursor=cursor, limit=1)
            self.assertEqual(resumed['items'][0]['text'], 'target local only')

    def test_default_export_and_stable_identities_remain_compatible(self):
        full = list(corpus.iter_export('synthetic', limit=3))
        full_items = [item for page in full for item in page['items']]
        self.assertEqual(len(full_items), 8)
        self.assertEqual(full[0]['source_total'], 8)
        self.assertEqual(full[0]['scan_scope'], 'full-history')
        self.assertNotIn('conversation_filter', full[0])
        selected = list(corpus.iter_export('synthetic', conversation=ROOM, limit=2))
        items = [item for page in selected for item in page['items']]
        self.assertEqual(items, [item for item in full_items if item['conversation_id'] == ROOM])
        self.assertEqual(items[0]['remote_id'], items[3]['remote_id'])
        self.assertNotEqual(items[0]['record_id'], items[3]['record_id'])
        self.assertEqual(items[0]['server_id'], '9223372036854775807')
        self.assertEqual(items[0]['source_locator'], {'shard': 'message/message_0.db', 'table': TABLE, 'row_key': 1, 'local_id': 1})
        for page in selected:
            self.assertEqual(page['source_identity'], self.binding['source_identity'])
            self.assertEqual(page['self_identity'], {'verified': False, 'username': None, 'evidence': None})
            self.assertTrue(all(item['is_self'] is None for item in page['items']))
        with self.assertRaisesRegex(RuntimeError, '会话过滤不匹配'):
            corpus.export('synthetic', cursor=full[0]['next_cursor'], conversation=ROOM)

    def test_time_window_and_filter_have_separate_counts_and_cursors(self):
        window = {'since': '2023-11-14T22:13:21Z', 'until': '2023-11-14T22:13:24Z'}
        with self.target_reads_only():
            result = corpus.stats('synthetic', conversation=ROOM, **window)
            self.assertEqual(result['source_total'], 4)
            self.assertEqual(result['all_source_total'], 5)
            self.assertEqual(result['scan_scope'], 'conversation-time-window')
            first = corpus.export('synthetic', conversation=ROOM, limit=1, **window)
            self.assertEqual(first['items'][0]['text'], 'target local only')
            with self.assertRaisesRegex(RuntimeError, '游标无效或快照已改变'):
                corpus.export('synthetic', conversation=ROOM, cursor=first['next_cursor'])
            following = list(corpus.iter_export('synthetic', conversation=ROOM, cursor=first['next_cursor'], limit=1, **window))
            self.assertEqual(sum(page['rows_returned'] for page in following), 3)

    def test_exact_filter_without_contact_entry_and_missing_table(self):
        with sqlite3.connect(self.root / 'contact' / 'contact.db') as db:
            db.execute('DELETE FROM contact WHERE username=?', (ROOM,))
        with self.target_reads_only():
            result = corpus.export('synthetic', conversation=ROOM)
            self.assertEqual({row['conversation_id'] for row in result['items']}, {ROOM})
            absent = corpus.stats('synthetic', conversation='synthetic-missing@chatroom')
            self.assertEqual(absent['source_total'], 0)
            empty = corpus.export('synthetic', conversation='synthetic-missing@chatroom')
            self.assertEqual(empty['items'], [])
            self.assertTrue(empty['complete'])

    def test_invalid_filter_rejected_before_snapshot_access(self):
        with patch.object(corpus, '_binding', side_effect=AssertionError('invalid filter reached snapshot')):
            for invalid in ('', '群名称', ROOM + ',' + OTHER, ' ' + ROOM, ROOM + '\n', '../db', 1, ['room'], 'a' * 241):
                for operation in (corpus.stats, corpus.export):
                    with self.assertRaisesRegex(RuntimeError, '精确的联系人或群聊 ID'):
                        operation('synthetic', conversation=invalid)

    def test_generation_change_rejects_resume(self):
        cursor = corpus.export('synthetic', conversation=ROOM, limit=1)['next_cursor']
        self.binding['snapshot_id'] = 'replacement-generation'
        with self.assertRaisesRegex(RuntimeError, '游标无效或快照已改变'):
            corpus.export('synthetic', conversation=ROOM, cursor=cursor)


class CorpusCliContractTests(unittest.TestCase):
    def test_real_parser_and_command_forward_filter_in_all_export_modes(self):
        # Execute only the parser's corpus block and cmd_corpus definition.
        # Never import/run the CLI bootstrap or discover a user's data folder.
        tree = ast.parse((CLI_ROOT / 'vchat').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'cmd_corpus')
        def starts_corpus(node):
            return isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and bool(node.value.args) and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == 'corpus'
        parent = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.If)) and any(starts_corpus(part) for part in node.body))
        start = next(index for index, node in enumerate(parent.body) if starts_corpus(node))
        block = []
        for node in parent.body[start:]:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'parse_args':
                break
            block.append(node)
        parser = argparse.ArgumentParser()
        namespace = {'sub': parser.add_subparsers(dest='cmd', required=True), 'DATA_DIR': Path('/synthetic-unused'), 'json': json, 'sys': sys}
        exec(compile(ast.Module(body=[function, *block], type_ignores=[]), '<isolated-corpus-cli>', 'exec'), namespace)
        cases = [(['stats'], 'stats'), (['export'], 'export'), (['export', '--stream'], 'iter_export'), (['export', '--pages', '1'], 'iter_export')]
        for argv, operation in cases:
            for filter_args, expected in [([], None), (['--conversation', ROOM], ROOM)]:
                args = parser.parse_args(['corpus', *argv, *filter_args])
                value = [{'complete': True}] if operation == 'iter_export' else {'complete': True}
                with patch.object(corpus, operation, return_value=value) as call, contextlib.redirect_stdout(io.StringIO()) as output:
                    args.func(args)
                self.assertEqual(call.call_args.kwargs['conversation'], expected)
                self.assertTrue(json.loads(output.getvalue())['complete'])


if __name__ == '__main__':
    unittest.main()
