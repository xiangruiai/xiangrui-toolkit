"""Isolated encrypted fixtures only: never opens a live WeChat database."""
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from vchat_core import crypto, decrypt_pipeline, snapshot


KEY = bytes(range(32))
SALT = bytes(range(16))


def encrypted_pages(count=2):
    result = []
    mac_key = crypto.derive_mac_key(KEY, SALT)
    for number in range(1, count + 1):
        payload = bytes([number]) * (4000 if number == 1 else 4016)
        iv = bytes([number + 30]) * 16
        cipher = Cipher(algorithms.AES(KEY), modes.CBC(iv)).encryptor()
        ciphertext = cipher.update(payload) + cipher.finalize()
        mac = hmac.new(mac_key, ciphertext + iv + struct.pack('<I', number), hashlib.sha512).digest()
        result.append((SALT if number == 1 else b'') + ciphertext + iv + mac)
    return b''.join(result)


class StableCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source' / 'message.db'
        self.source.parent.mkdir()
        self.source.write_bytes(encrypted_pages())
        self.target = self.base / 'generation' / 'decrypted' / 'message.db'
        self.target.parent.mkdir(parents=True)
        self.delay = patch.object(decrypt_pipeline.time, 'sleep')
        self.delay.start()
        self.addCleanup(self.delay.stop)

    def decrypt(self):
        return decrypt_pipeline._decrypt_stable_db(
            self.source, self.target, KEY.hex(), self.target.parent.parent)

    def test_all_pages_authenticated_and_private_capture_removed(self):
        result = self.decrypt()
        self.assertTrue(result['ok'])
        self.assertTrue(result['verified'])
        self.assertEqual(result['capture_attempts'], 1)
        self.assertEqual(result['stable_capture']['source'], snapshot.fingerprint(self.source))
        self.assertEqual(result['stable_capture']['output'], snapshot.fingerprint(self.target))
        self.assertTrue(self.target.read_bytes().startswith(crypto.SQLITE_HEADER))
        self.assertEqual(self.target.stat().st_size, 8192)
        self.assertEqual(list(self.target.parent.parent.glob('.vchat-capture-*')), [])

    def test_live_write_during_copy_retries_only_this_database(self):
        original_fingerprint = snapshot.fingerprint
        observations = 0

        def observe(path):
            nonlocal observations
            if Path(path) == self.source:
                observations += 1
                if observations == 2:
                    self.source.write_bytes(encrypted_pages(3))
            return original_fingerprint(path)

        with patch.object(snapshot, 'fingerprint', side_effect=observe):
            result = self.decrypt()
        self.assertTrue(result['ok'])
        self.assertEqual(result['capture_attempts'], 2)
        self.assertEqual(result['pages'], 3)
        self.assertEqual(self.target.stat().st_size, 3 * crypto.PAGE_SIZE)

    def test_write_after_stable_copy_does_not_invalidate_older_verified_copy(self):
        captured_fingerprint = snapshot.fingerprint(self.source)
        original = decrypt_pipeline._capture_encrypted_db

        def capture(*args):
            result = original(*args)
            self.source.write_bytes(encrypted_pages(3))
            return result

        with patch.object(decrypt_pipeline, '_capture_encrypted_db', side_effect=capture):
            result = self.decrypt()
        self.assertTrue(result['ok'])
        self.assertEqual(result['stable_capture']['source'], captured_fingerprint)
        self.assertEqual(result['pages'], 2)
        self.assertNotEqual(captured_fingerprint, snapshot.fingerprint(self.source))

    def test_continuously_unstable_capture_stops_after_three_attempts(self):
        with patch.object(decrypt_pipeline, '_capture_encrypted_db',
                          side_effect=decrypt_pipeline._UnstableSource('changed')) as capture:
            result = self.decrypt()
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'source-unstable')
        self.assertEqual(capture.call_count, 3)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.parent.glob('.vchat-capture-*')), [])

    def test_corrupt_page_is_never_published_as_success(self):
        content = bytearray(self.source.read_bytes())
        content[crypto.PAGE_SIZE + 100] ^= 1
        self.source.write_bytes(content)
        result = self.decrypt()
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'decryption-failed')
        self.assertEqual(result['capture_attempts'], 3)
        self.assertIn('HMAC', result['err'])
        self.assertFalse(self.target.exists())

    def test_empty_or_unverified_first_page_rejected(self):
        for content in (b'', bytes(crypto.PAGE_SIZE), b'incomplete'):
            with self.subTest(size=len(content)):
                self.source.write_bytes(content)
                result = self.decrypt()
                self.assertFalse(result['ok'])
                self.assertFalse(self.target.exists())

    def test_unallocated_zero_pages_after_first_page_still_supported(self):
        self.source.write_bytes(encrypted_pages(1) + bytes(crypto.PAGE_SIZE))
        result = self.decrypt()
        self.assertTrue(result['ok'])
        self.assertEqual(self.target.read_bytes()[crypto.PAGE_SIZE:], bytes(crypto.PAGE_SIZE))

    def test_symlink_or_hardlinked_sources_not_accepted(self):
        original = self.source.parent / 'original.db'
        self.source.rename(original)
        self.source.symlink_to(original)
        self.assertFalse(self.decrypt()['ok'])
        self.source.unlink()
        os.link(original, self.source)
        self.assertFalse(self.decrypt()['ok'])
        self.assertFalse(self.target.exists())

    def test_short_read_cannot_return_verified_with_missing_pages(self):
        real_open = open
        source_reads = 0

        def open_truncated(path, mode='r', *args, **kwargs):
            nonlocal source_reads
            if Path(path) == self.source and mode == 'rb':
                source_reads += 1
                if source_reads == 2:
                    return io.BytesIO(encrypted_pages(1))
            return real_open(path, mode, *args, **kwargs)

        with patch.object(crypto, 'open', side_effect=open_truncated, create=True):
            with self.assertRaisesRegex(ValueError, '截断 page=2'):
                crypto.decrypt_db(self.source, self.target, KEY.hex())

    def test_pipeline_binds_each_db_to_its_own_stable_capture(self):
        second = self.source.parent / 'second.db'
        second.write_bytes(encrypted_pages())
        cache = self.base / 'synthetic-keys.json'
        cache.write_text(json.dumps({'message.db': KEY.hex(), 'second.db': KEY.hex()}))
        real_decrypt = crypto.decrypt_db
        first = True

        def decrypt_and_receive_new_message(*args, **kwargs):
            nonlocal first
            if first:
                first = False
                second.write_bytes(encrypted_pages(3))
            return real_decrypt(*args, **kwargs)

        with patch.object(decrypt_pipeline, 'find_db_storage', return_value=self.source.parent), \
                patch.object(crypto, 'decrypt_db', side_effect=decrypt_and_receive_new_message), \
                patch.object(decrypt_pipeline, 'find_wechat_pids', side_effect=AssertionError('must not scan processes')):
            summary = decrypt_pipeline.full_pipeline(
                self.base / 'unused-scanner', self.base, cached_keys=cache, output_root=self.target.parent)
        self.assertEqual(summary['dbs_decrypted_ok'], 2)
        self.assertEqual(summary['dbs_failed'], 0)
        self.assertEqual(summary['source_fingerprints']['second.db'], snapshot.fingerprint(second))
        self.assertEqual(summary['results']['second.db']['pages'], 3)
        self.assertEqual(summary['results']['message.db']['capture_attempts'], 1)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'snapshots'
        self.control = self.base / 'control'
        self.control.mkdir()
        self.storage = self.base / 'source'
        self.storage.mkdir()
        self.source = self.storage / 'message.db'
        self.source.write_bytes(encrypted_pages())
        self.output = self.root / ('a' * 32) / 'decrypted'
        self.output.mkdir(parents=True)
        self.target = self.output / 'message.db'
        self.patchroot = patch.object(snapshot, 'snapshot_root', return_value=self.root)
        self.patchroot.start()
        self.addCleanup(self.patchroot.stop)
        self.delay = patch.object(decrypt_pipeline.time, 'sleep')
        self.delay.start()
        self.addCleanup(self.delay.stop)

    def summary(self):
        result = decrypt_pipeline._decrypt_stable_db(self.source, self.target, KEY.hex(), self.output.parent)
        self.assertTrue(result['ok'])
        return {'db_storage': str(self.storage), 'results': {'message.db': result},
                'source_fingerprints': {'message.db': result['stable_capture']['source']}}

    def test_publish_binds_capture_without_demanding_global_live_quiescence(self):
        summary = self.summary()
        self.source.write_bytes(encrypted_pages(3))
        receipt = snapshot.publish(self.control, self.output, summary)
        self.assertEqual(receipt['coverage']['successful_databases'], 1)
        self.assertTrue(receipt['coverage']['local_source_complete'])
        self.assertFalse(receipt['coverage']['upstream_sync_complete'])
        self.assertEqual(receipt['source_files'], summary['source_fingerprints'])
        self.assertEqual(snapshot.active(self.control), receipt)
        self.assertEqual(self.target.stat().st_size, 8192)

    def test_output_modified_between_decrypt_and_publish_is_rejected(self):
        summary = self.summary()
        self.target.write_bytes(b'damaged output')
        with self.assertRaisesRegex(RuntimeError, '没有稳定成功'):
            snapshot.publish(self.control, self.output, summary)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.control / snapshot.POINTER).exists())
        receipt = json.loads((self.output.parent / 'receipt.json').read_text())
        self.assertEqual(receipt['coverage']['failed'], {'message.db': 'output-verification-failed'})

    def test_failed_capture_and_missing_keys_remain_explicit_partial_coverage(self):
        summary = self.summary()
        summary['source_fingerprints'].update({'busy.db': [1, 2, 3, 4, 5], 'missing.db': [1, 3, 3, 4, 5]})
        summary['results']['busy.db'] = {'ok': False, 'reason': 'source-unstable'}
        receipt = snapshot.publish(self.control, self.output, summary)
        self.assertEqual(receipt['state'], 'partial')
        self.assertEqual(receipt['coverage']['failed'], {'busy.db': 'source-unstable'})
        self.assertEqual(receipt['coverage']['missing_keys'], ['missing.db'])
        self.assertFalse(receipt['coverage']['local_source_complete'])

    def test_legacy_summary_without_stable_capture_still_checks_source(self):
        summary = self.summary()
        del summary['results']['message.db']['stable_capture']
        self.source.write_bytes(encrypted_pages(3))
        with self.assertRaisesRegex(RuntimeError, '没有稳定成功'):
            snapshot.publish(self.control, self.output, summary)
        self.assertFalse((self.control / snapshot.POINTER).exists())


if __name__ == '__main__':
    unittest.main()
