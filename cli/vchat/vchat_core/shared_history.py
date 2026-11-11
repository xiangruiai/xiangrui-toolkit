"""Resolve one group's shared-history attachment from its existing local files.

No network, key extraction, source writes, or cross-conversation body scans.
The CLI caller must bind account_root to the active snapshot source identity.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import time
import xml.etree.ElementTree as ET

MAX_PAYLOAD = 1024 * 1024
MAX_SCAN_FILES = 50000
MAX_FILENAME_SCAN = 1000000
MAX_CANDIDATES = 128
MAX_READ_BYTES = 16 * 1024 * 1024
SCAN_SECONDS = 30
HEX32 = re.compile(r"[0-9a-fA-F]{32}\Z")


def _xml(data):
    if len(data) > MAX_PAYLOAD or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("unsupported-or-oversized-xml")
    return ET.fromstring(data)


def parse_references(content):
    """Return internal references; callers must not serialize the AES fields."""
    if not isinstance(content, str) or len(content) > MAX_PAYLOAD:
        raise ValueError("invalid-anchor-content")
    start = content.find("<sysmsg")
    if start < 0:
        return []
    root = _xml(content[start:].encode("utf-8"))
    refs = []
    for link in root.findall(".//link[@type='link_history']"):
        history_id = (link.findtext("historyid") or "").strip()
        for variant, prefix, length_tag in (
            ("legacy", "", "filelength"),
            ("newformat", "newformat", "newfromatfilelength"),
        ):
            digest = (link.findtext(prefix + "md5") or "").strip().lower()
            key = (link.findtext(prefix + "aeskey") or "").strip()
            raw_length = link.findtext(length_tag)
            if raw_length is None and prefix:
                raw_length = link.findtext("newformatfilelength")
            if not digest and not key and raw_length is None:
                continue
            if not HEX32.fullmatch(digest) or not HEX32.fullmatch(key):
                raise ValueError("invalid-shared-history-reference")
            raw_count = link.findtext(prefix + "msgcount") or "0"
            if not re.fullmatch(r"[0-9]{1,8}", raw_length or "") or not re.fullmatch(r"[0-9]{1,5}", raw_count):
                raise ValueError("invalid-shared-history-size-or-count")
            length = int(raw_length)
            count = int(raw_count)
            if not 0 < length <= MAX_PAYLOAD or not 0 <= count <= 10000:
                raise ValueError("invalid-shared-history-size-or-count")
            refs.append({"variant": variant, "md5": digest, "aeskey": key,
                         "length": length, "count": count, "history_id": history_id})
    return refs


def _anchor(cache, username, local_id):
    table = "Msg_" + hashlib.md5(username.encode()).hexdigest()
    matches, scanned, hits = [], 0, 0
    for path in sorted((cache._root / "message").glob("message_*.db")):
        if not re.fullmatch(r"message_[0-9]+\.db", path.name):
            continue
        scanned += 1
        conn = cache.get("message/" + path.name)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        hits += 1
        rows = conn.execute(
            'SELECT message_content FROM "' + table + '" WHERE local_id=? LIMIT 3',
            (local_id,),
        ).fetchall()
        matches.extend(row[0] for row in rows)
    if len(matches) != 1:
        raise ValueError("anchor-not-found" if not matches else "ambiguous-anchor-local-id")
    from .content import decompress_content
    return decompress_content(matches[0]), {"message_shards_checked": scanned, "group_tables_checked": hits,
                                            "anchor_rows": 1}


def _columns(conn, table):
    return [row[1] for row in conn.execute('PRAGMA table_info("' + table.replace('"', '""') + '")')]


def _resource_hints(cache, username, local_id):
    """Inspect schemas and only the exact group's exact message resource rows."""
    summary = {"status": "unavailable", "matched_rows": 0, "schemas": {}}
    hints = set()
    try:
        conn = cache.get("message/message_resource.db")
    except FileNotFoundError:
        return hints, summary
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in sorted(tables):
        if re.search(r"resource|history|record|cdn", name, re.I):
            if len(summary["schemas"]) >= 40:
                summary["schema_list_truncated"] = True
                break
            summary["schemas"][name] = _columns(conn, name)[:100]
    if not {"ChatName2Id", "MessageResourceInfo"}.issubset(tables):
        summary["status"] = "required-tables-unavailable"
        return hints, summary
    chat_columns = _columns(conn, "ChatName2Id")
    columns = _columns(conn, "MessageResourceInfo")
    if "user_name" not in chat_columns or not {"chat_id", "message_local_id"}.issubset(columns):
        summary["status"] = "unsupported-resource-schema"
        return hints, summary
    chat_ids = conn.execute("SELECT rowid FROM ChatName2Id WHERE user_name=? LIMIT 2", (username,)).fetchall()
    if len(chat_ids) != 1:
        summary["status"] = "group-not-indexed" if not chat_ids else "ambiguous-group-index"
        return hints, summary
    rows = conn.execute("SELECT * FROM MessageResourceInfo WHERE chat_id=? AND message_local_id=? LIMIT 6",
                        (chat_ids[0][0], local_id)).fetchall()
    summary.update(status="checked", matched_rows=len(rows), rows_truncated=len(rows) > 5)
    for row in rows[:5]:
        for value in row:
            if isinstance(value, str):
                raw = value.encode("utf-8")
            elif isinstance(value, bytes):
                raw = value
            else:
                continue
            if len(raw) > MAX_PAYLOAD:
                summary["oversized_resource_values_skipped"] = summary.get("oversized_resource_values_skipped", 0) + 1
                continue
            # Hints remain internal; raw resource payloads may contain keys.
            hints.update(m.decode().lower() for m in re.findall(rb"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])", raw))
    return hints, summary


def _verified_plaintext(raw, ref):
    def good(value):
        return len(value) == ref["length"] and hashlib.md5(value).hexdigest() == ref["md5"]
    if good(raw):
        return raw, "plaintext-md5-and-length"
    if not raw or len(raw) % 16:
        return None
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    decryptor = Cipher(algorithms.AES(bytes.fromhex(ref["aeskey"])), modes.ECB()).decryptor()
    decoded = decryptor.update(raw) + decryptor.finalize()
    padding = decoded[-1]
    if 1 <= padding <= 16 and decoded[-padding:] == bytes([padding]) * padding:
        plain = decoded[:-padding]
        if good(plain):
            return plain, "aes-ecb-pkcs7-md5-and-length"
    return None


def _payload_shape(plain):
    try:
        root = _xml(plain)
    except (ValueError, ET.ParseError):
        return {"format": "binary-or-unparsed", "parsed_message_count": None}, ".bin"
    # Count top-level record items, not dataitems nested in forwarded records.
    datalist = next(root.iter("datalist"), None)
    items = datalist.findall("dataitem") if datalist is not None else []
    return {"format": "xml", "parsed_message_count": len(items) if items else None}, ".xml"


def _read_regular(path, size):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        # WeChat legitimately uses hardlinks: their bytes are still read-only.
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise ValueError("candidate-not-regular-or-changed")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_PAYLOAD + 17)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("candidate-changed-during-read")
        return raw
    finally:
        os.close(fd)


def _write_verified(output_dir, local_id, ref, plain, extension):
    folder = Path(output_dir).absolute()
    for node in (folder, *folder.parents):
        if node.is_symlink():
            raise ValueError("output-path-contains-symlink")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"shared-history-{local_id}-{ref['variant']}-{ref['md5']}{extension}"
    path = folder / name
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if _read_regular(path, len(plain)) != plain:
            raise ValueError("existing-output-content-mismatch")
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(plain)
    return name


def _fingerprint_search(account, group_root, refs, consume):
    """Global attachment names only; open bytes only after a reference match."""
    coverage = {"roots": ["msg", "cache"], "scope": "reference-filename-match-only",
                "files_name_checked": 0, "fingerprint_name_matches": 0, "candidates_read": 0,
                "bytes_read": 0, "traversal_complete": True, "skipped_symlinks": 0,
                "skipped_errors": 0, "unavailable_roots": [], "excluded_target_group_subtree": True}
    patterns = [re.compile(r"(?<![0-9a-f])" + re.escape(ref["md5"]) + r"(?![0-9a-f])") for ref in refs]
    patterns += [re.compile(r"(?<![0-9])" + re.escape(ref["history_id"]) + r"(?![0-9])")
                 for ref in refs if re.fullmatch(r"[0-9]{8,32}", ref["history_id"])]
    deadline = time.monotonic() + SCAN_SECONDS
    def onerror(_):
        coverage["skipped_errors"] += 1
    for root_name in coverage["roots"]:
        root = account / root_name
        if root.is_symlink():
            coverage["skipped_symlinks"] += 1
            continue
        if not root.is_dir():
            coverage["unavailable_roots"].append(root_name)
            continue
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            kept = []
            for name in dirs:
                child = Path(directory) / name
                if child == group_root:
                    continue
                if child.is_symlink():
                    coverage["skipped_symlinks"] += 1
                else:
                    kept.append(name)
            dirs[:] = kept
            for name in files:
                if (coverage["files_name_checked"] >= MAX_FILENAME_SCAN or coverage["candidates_read"] >= MAX_CANDIDATES
                        or coverage["bytes_read"] >= MAX_READ_BYTES or time.monotonic() >= deadline):
                    coverage["traversal_complete"] = False
                    coverage["stopped_reason"] = "bounded-search-budget"
                    return coverage
                coverage["files_name_checked"] += 1
                lower = name.lower()
                if not any(pattern.search(lower) for pattern in patterns):
                    continue
                if re.search(r"\.(db|sqlite|sqlite3)(-wal|-shm)?$", lower):
                    continue
                coverage["fingerprint_name_matches"] += 1
                path = Path(directory) / name
                try:
                    st = path.lstat()
                    if stat.S_ISLNK(st.st_mode):
                        coverage["skipped_symlinks"] += 1
                        continue
                    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_PAYLOAD + 16:
                        continue
                    raw = _read_regular(path, st.st_size)
                    coverage["candidates_read"] += 1
                    coverage["bytes_read"] += len(raw)
                except (OSError, ValueError):
                    coverage["skipped_errors"] += 1
                    continue
                if consume(path, raw):
                    coverage["traversal_complete"] = False
                    coverage["stopped_reason"] = "verified-payload-found"
                    return coverage
    return coverage


def inspect_shared_history(username, local_id, account_root, output_dir=None, cache=None):
    """Inspect/export one anchor; account_root must be source-bound by the caller.

    Returns JSON-safe metadata with relative paths; no keys or raw XML are logged.
    Verified payloads are exported only when output_dir is provided.
    """
    if not re.fullmatch(r"[0-9]+@chatroom", username) or type(local_id) is not int or local_id <= 0:
        raise ValueError("exact-group-id-and-positive-local-id-required")
    if cache is None:
        from .cache import default_cache
        cache = default_cache()
    account = Path(account_root).absolute()
    for node in (account, *account.parents):
        if node.is_symlink():
            raise ValueError("account-path-contains-symlink")
    content, coverage = _anchor(cache, username, local_id)
    refs = parse_references(content)
    public_refs = [{k: ref[k] for k in ("variant", "md5", "length", "count")} for ref in refs]
    result = {"command": "shared-history", "username": username, "local_id": local_id,
              "references": public_refs, "verified": [], "coverage": coverage, "gaps": []}
    if not refs:
        result.update(status="no-shared-history-reference")
        return result
    hints, resource = _resource_hints(cache, username, local_id)
    result["resource_index"] = resource
    group_root = account / "msg" / "attach" / hashlib.md5(username.encode()).hexdigest()
    coverage.update(scope="target-group-attachment-subtree-only", files_statted=0, candidates_read=0,
                    bytes_read=0, traversal_complete=True, skipped_symlinks=0, skipped_errors=0,
                    network_attempted=False, key_extraction_attempted=False,
                    other_conversation_bodies_read=False)
    for node in (group_root, group_root.parent, group_root.parent.parent):
        if node.is_symlink():
            raise ValueError("group-attachment-path-contains-symlink")
    if not group_root.is_dir():
        result["gaps"].append("target-group-attachment-directory-unavailable")
    names = hints | {ref["md5"] for ref in refs} | {ref["history_id"].lower() for ref in refs if ref["history_id"]}
    sizes = {n for ref in refs for n in (ref["length"], (ref["length"] // 16 + 1) * 16)}
    deadline = time.monotonic() + SCAN_SECONDS
    secrets = [ref["aeskey"] for ref in refs]
    seen = set()
    def consume(path, raw):
        found = False
        for ref in refs:
            verified = _verified_plaintext(raw, ref)
            if verified is None or ref["md5"] in seen:
                continue
            plain, method = verified
            shape, extension = _payload_shape(plain)
            relative = str(path.relative_to(account))
            for secret in secrets:
                relative = relative.replace(secret, "[redacted]").replace(secret.lower(), "[redacted]")
            entry = {"variant": ref["variant"], "source_relative": relative, "method": method,
                     "md5": ref["md5"], "bytes": len(plain), "expected_message_count": ref["count"], **shape}
            entry["message_count_verified"] = shape["parsed_message_count"] == ref["count"]
            if output_dir is not None:
                entry["exported_file"] = _write_verified(output_dir, local_id, ref, plain, extension)
            result["verified"].append(entry)
            seen.add(ref["md5"])
            found = True
        return found
    def walk_error(_):
        coverage["skipped_errors"] += 1
    for directory, dirs, files in os.walk(group_root, followlinks=False, onerror=walk_error):
        keep = []
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                coverage["skipped_symlinks"] += 1
            else:
                keep.append(name)
        dirs[:] = keep
        for name in files:
            if (coverage["files_statted"] >= MAX_SCAN_FILES or coverage["candidates_read"] >= MAX_CANDIDATES
                    or coverage["bytes_read"] >= MAX_READ_BYTES or time.monotonic() >= deadline):
                coverage["traversal_complete"] = False
                break
            path = Path(directory) / name
            try:
                st = path.lstat()
                coverage["files_statted"] += 1
                if stat.S_ISLNK(st.st_mode):
                    coverage["skipped_symlinks"] += 1
                    continue
                if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= MAX_PAYLOAD + 16:
                    continue
                if st.st_size not in sizes and not any(token in name.lower() for token in names):
                    continue
                raw = _read_regular(path, st.st_size)
                coverage["candidates_read"] += 1
                coverage["bytes_read"] += len(raw)
            except (OSError, ValueError):
                coverage["skipped_errors"] += 1
                continue
            consume(path, raw)
        if not coverage["traversal_complete"]:
            break
    if not result["verified"]:
        result["fingerprint_search"] = _fingerprint_search(account, group_root, refs, consume)
        global_search = result["fingerprint_search"]
        if global_search["skipped_errors"] or global_search.get("stopped_reason") == "bounded-search-budget":
            result["gaps"].append("fingerprint-search-incomplete")
    if not result["verified"]:
        result["gaps"].append("no-reference-matching-local-payload-found-in-scoped-search")
    if coverage["skipped_errors"] or not coverage["traversal_complete"]:
        result["gaps"].append("local-search-incomplete")
    if any(not entry["message_count_verified"] for entry in result["verified"]):
        result["gaps"].append("verified-payload-requires-message-format-parsing")
    result["status"] = "verified-local-payload" if result["verified"] else "not-found-locally"
    return result
