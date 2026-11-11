"""Recover an image key through vchat, without restarting or changing WeChat.

Only caller-selected attachment samples are inspected. Key material stays in the
local CLI config and is never included in command output.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .image_codec import V2_MAGIC_6, detect_format


def recover_image_key(samples, config_path, scanner, timeout=60):
    samples = [Path(p) for p in samples]
    blocks = []
    for sample in samples:
        with sample.open('rb') as stream:
            head = stream.read(31)
        if len(head) == 31 and head[:6] == V2_MAGIC_6:
            blocks.append((sample, head[15:31]))
    if not blocks:
        return {'status': 'no-v2-sample'}
    config_path = Path(config_path)
    # Fail on malformed config; never replace it with an empty one.
    cfg = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(cfg, dict):
        raise ValueError('invalid vchat config')
    old = cfg.get('image_aes_key')
    if old:
        return {'status': 'key-already-configured'}
    proc = subprocess.run(['pgrep', '-f', 'WeChat.app/Contents/MacOS/WeChat$'],
                          capture_output=True, text=True)
    pids = proc.stdout.split()
    if len(pids) != 1:
        return {'status': 'wechat-process-not-unique', 'process_count': len(pids)}
    if not Path(scanner).is_file():
        return {'status': 'scanner-unavailable'}
    try:
        result = subprocess.run([str(scanner), '--pid', pids[0], '--sample', str(blocks[0][0])],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'status': 'scan-timeout', 'timeout_seconds': timeout}
    if result.returncode:
        status = 'process-read-denied' if 'task_for_pid' in result.stderr else 'key-not-found'
        return {'status': status, 'scanner_exit_code': result.returncode}
    try:
        key_hex = json.loads(result.stdout)['image_aes_key']
        if not isinstance(key_hex, str) or not re.fullmatch(r'[0-9a-fA-F]{32}', key_hex):
            raise ValueError('invalid key')
        key = bytes.fromhex(key_hex)
        for _, block in blocks:
            dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
            if detect_format(dec.update(block) + dec.finalize()) == 'bin':
                return {'status': 'candidate-validation-failed'}
    except (ValueError, KeyError, TypeError):
        return {'status': 'invalid-scanner-result'}
    # Re-read before merging to preserve concurrent config updates.
    current = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(current, dict):
        raise ValueError('invalid vchat config')
    if current.get('image_aes_key'):
        return {'status': 'config-changed-retry'}
    current['image_aes_key'] = key_hex
    current['_image_key_sample'] = str(blocks[0][0])
    # Existing paths and non-image configuration are deliberately preserved.
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.image-key-', dir=str(config_path.parent))
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(current, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'status': 'recovered', 'validated_samples': len(blocks)}
