"""Durable per-project chat snapshots, revision copies and response capture."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time

import hub_chats as references

MAX_BODY = 64 * 1024 * 1024
KEEP_REVISIONS = 20
KEEP_DAYS = 30
LOCK = threading.RLock()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".history-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Vault:
    def __init__(self, data_root, slug, port):
        base = Path(data_root).resolve()
        if not references.ID.fullmatch(slug):
            raise ValueError("Invalid project")
        self.root = base / slug / "chat-backups"
        self.root.resolve().relative_to(base / slug)
        self.refs = references.Store(data_root, slug, port)
        self.port = int(port)

    def folder(self, chat_id):
        if not isinstance(chat_id, str) or not references.ID.fullmatch(chat_id):
            raise ValueError("Invalid chat ID")
        folder = self.root / ("chat-" + chat_id)
        folder.resolve().relative_to(self.root)
        return folder

    def _file(self, folder, name):
        path = folder / name
        path.resolve().relative_to(self.root.resolve())
        return path

    def _load_file(self, path):
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rb") as source:
                    raw = source.read(MAX_BODY + 1)
            else:
                if path.stat().st_size > MAX_BODY:
                    return None
                raw = path.read_bytes()
            if len(raw) > MAX_BODY:
                return None
            doc = json.loads(raw)
            if not isinstance(doc, dict) or not isinstance(doc.get("payload"), dict):
                return None
            return doc if hashlib.sha256(encoded(doc["payload"])).hexdigest() == doc.get("revision") else None
        except (OSError, ValueError, TypeError, RecursionError):
            return None

    def load(self, chat_id, kind):
        folder = self.folder(chat_id)
        doc = self._load_file(self._file(folder, "latest-" + kind + ".json"))
        if doc and doc["payload"].get("id") == chat_id:
            return doc
        revisions = self._file(folder, "revisions-" + kind)
        for path in sorted(revisions.glob("*.json.gz"), reverse=True):
            path.resolve().relative_to(revisions.resolve())
            doc = self._load_file(path)
            if doc and doc["payload"].get("id") == chat_id:
                return doc
        return None

    def archived(self, chat_id):
        path = self._file(self.folder(chat_id), "state.json")
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("archived") is True
        except FileNotFoundError:
            return False
        except (OSError, ValueError, AttributeError):
            # A damaged deletion marker must not silently resurrect a chat.
            return True

    def set_archived(self, chat_id, archived):
        if not isinstance(archived, bool):
            raise ValueError("Expected archive state")
        with LOCK:
            atomic(self._file(self.folder(chat_id), "state.json"),
                   encoded({"archived": archived, "at": int(time.time() * 1000)}))

    def _save(self, payload, conflict=False):
        raw_payload = encoded(payload)
        if len(raw_payload) > MAX_BODY - 1024:
            raise ValueError("Chat backup exceeds the size limit")
        revision = hashlib.sha256(raw_payload).hexdigest()
        doc = {"revision": revision, "saved_at": int(time.time() * 1000), "payload": payload}
        raw = encoded(doc)
        folder = self.folder(payload["id"])
        kind = payload["source"]
        versions = self._file(folder, ("conflicts-" if conflict else "revisions-") + kind)
        # Deduplicate retries, including stale clients retrying the same conflict.
        if not any(versions.glob("*-" + revision[:16] + ".json.gz")):
            atomic(self._file(versions, "%013d-%s.json.gz" % (doc["saved_at"], revision[:16])), gzip.compress(raw, 3))
        if not conflict:
            atomic(self._file(folder, "latest-" + kind + ".json"), raw)
            daily = self._file(folder, "daily-" + kind)
            stamp = time.strftime("%Y-%m-%d", time.gmtime(doc["saved_at"] / 1000))
            checkpoint = self._file(daily, stamp + ".json.gz")
            if not checkpoint.exists():
                atomic(checkpoint, gzip.compress(raw, 3))
            self._prune(daily, KEEP_DAYS)
        self._prune(versions, KEEP_REVISIONS)
        return doc

    def _prune(self, folder, keep):
        for path in sorted(folder.glob("*.json.gz"), reverse=True)[keep:]:
            path.resolve().relative_to(folder.resolve())
            path.unlink()

    def save_native(self, chat, base_revision=None):
        conversation, messages = chat.get("conversation"), chat.get("messages")
        if not isinstance(conversation, dict) or not isinstance(messages, list) or len(messages) > 20000:
            raise ValueError("Invalid native snapshot")
        chat_id = conversation.get("id")
        self.folder(chat_id)
        ids = [m.get("id") for m in messages if isinstance(m, dict)]
        if (len(ids) != len(messages) or any(not isinstance(i, str) or not i or len(i) > 200 for i in ids)
                or len(set(ids)) != len(ids) or any(m.get("convId") != chat_id for m in messages)):
            raise ValueError("Invalid native message IDs")
        if conversation.get("currNode") and conversation["currNode"] not in ids:
            raise ValueError("Incomplete native snapshot")
        known = set(ids)
        if any(m.get("parent") is not None and m.get("parent") not in known for m in messages):
            raise ValueError("Incomplete native parents")
        meaningful = any(m.get("role") in ("user", "assistant", "tool") and
                         (references.text_of(m.get("content")).strip() or m.get("extra") or m.get("toolCalls")) for m in messages)
        payload = {"format": 1, "id": chat_id, "source": "native", "title": str(conversation.get("name") or "Untitled chat")[:300],
                   "updated_at": references.number(conversation.get("lastModified")), "conversation": conversation,
                   "messages": sorted(messages, key=lambda m: m["id"]), "meaningful": meaningful}
        revision = hashlib.sha256(encoded(payload)).hexdigest()
        with LOCK:
            if self.archived(chat_id):
                return {"state": "archived", "revision": None}
            old = self.load(chat_id, "native")
            fallback = self.load(chat_id, "fallback")
            if not meaningful and ((old and old["payload"].get("meaningful")) or
                                   (fallback and fallback["payload"].get("messages"))):
                return {"state": "protected-empty", "revision": old["revision"] if old else None}
            if not old and fallback and len(references.normalized_messages(messages)) < len(fallback["payload"]["messages"]):
                self._save(payload, conflict=True)
                return {"state": "protected-partial", "revision": None, "candidate_preserved": True}
            if old:
                if revision == old["revision"]:
                    return {"state": "unchanged", "revision": revision}
                if (payload["updated_at"] < old["payload"]["updated_at"] or base_revision != old["revision"]):
                    self._save(payload, conflict=True)
                    return {"state": "conflict", "revision": old["revision"], "candidate_preserved": True}
                old_ids = {m["id"] for m in old["payload"]["messages"]}
                if (old["payload"].get("meaningful") and not old_ids.intersection(ids) and
                        conversation.get("recoveredFromHistoryRevision") != old["revision"]):
                    self._save(payload, conflict=True)
                    return {"state": "protected-partial", "revision": old["revision"], "candidate_preserved": True}
            saved = self._save(payload)
            return {"state": "saved", "revision": saved["revision"]}

    def save_fallback(self, chat_id, messages, title="Untitled chat", complete=False, updated_at=None, expected_revision=None):
        self.folder(chat_id)
        normalized = references.normalized_messages(messages)
        payload = {"format": 1, "id": chat_id, "source": "fallback", "title": str(title)[:300],
                   "updated_at": references.number(updated_at) or int(time.time() * 1000),
                   "messages": normalized, "complete": bool(complete)}
        with LOCK:
            old = self.load(chat_id, "fallback")
            if old and expected_revision and old["revision"] != expected_revision:
                self._save(payload, conflict=True)
                return dict(old, conflict=True)
            if old and (not normalized or payload["updated_at"] < old["payload"]["updated_at"]):
                return old
            if old and payload == old["payload"]:
                return old
            return self._save(payload)

    def seed_references(self):
        for path in self.refs.root.glob("chat-*.json"):
            chat_id = path.name[5:-5]
            try:
                with LOCK:
                    if self.load(chat_id, "fallback") or self.load(chat_id, "native"):
                        continue
                    record = self.refs.load(chat_id, archived=True)
                    if not record:
                        continue
                    self.save_fallback(chat_id, record["messages"], record["title"], updated_at=record["updated_at"])
                    if record.get("archived"):
                        self.set_archived(chat_id, True)
            except (ValueError, OSError, TypeError):
                continue

    def versions(self, chat_id):
        folder, rows, seen = self.folder(chat_id), [], set()
        for prefix in ("revisions", "conflicts", "daily"):
            for kind in ("native", "fallback"):
                directory = self._file(folder, prefix + "-" + kind)
                for path in directory.glob("*.json.gz"):
                    path.resolve().relative_to(directory.resolve())
                    doc = self._load_file(path)
                    if not doc or doc["payload"].get("id") != chat_id or doc["revision"] in seen:
                        continue
                    seen.add(doc["revision"])
                    rows.append({"revision": doc["revision"], "saved_at": doc["saved_at"], "source": kind,
                                 "conflict": prefix == "conflicts", "message_count": len(doc["payload"]["messages"])})
        return {"versions": sorted(rows, key=lambda r: r["saved_at"], reverse=True)}

    def read(self, chat_id, revision=None):
        native, fallback = self.load(chat_id, "native"), self.load(chat_id, "fallback")
        if not native and not fallback:
            raise KeyError("Chat backup not found")
        # The server copy also retains the last answer if the browser closed
        # before saving it. A later native snapshot restores full UI metadata.
        use_native = bool(native and (not fallback or native["saved_at"] >= fallback["saved_at"]))
        chosen = native if use_native else fallback
        if revision:
            if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
                raise ValueError("Invalid history revision")
            chosen = None
            folder = self.folder(chat_id)
            for prefix in ("revisions", "conflicts", "daily"):
                for kind in ("native", "fallback"):
                    directory = self._file(folder, prefix + "-" + kind)
                    for path in directory.glob("*" + revision[:16] + ".json.gz" if prefix != "daily" else "*.json.gz"):
                        path.resolve().relative_to(directory.resolve())
                        doc = self._load_file(path)
                        if doc and doc["revision"] == revision and doc["payload"].get("id") == chat_id:
                            chosen = doc
            if not chosen:
                raise KeyError("History revision not found")
            use_native = chosen["payload"]["source"] == "native"
        p = chosen["payload"]
        return {"chat_id": chat_id, "title": p["title"], "updated_at": p["updated_at"],
                "revision": chosen["revision"], "native_revision": native["revision"] if native else None,
                "saved_at": chosen["saved_at"], "archived": self.archived(chat_id),
                "source": p["source"], "conversation": p.get("conversation"), "messages": p["messages"],
                "text_only": not use_native or bool(p.get("conversation", {}).get("recoveredFromSharedCopy", {}).get("textOnly")),
                "complete": p.get("complete", True)}

    def list(self, include_archived=False, offset=0, limit=100):
        self.seed_references()
        rows = []
        for folder in self.root.glob("chat-*"):
            if not folder.is_dir():
                continue
            try:
                data = self.read(folder.name[5:])
                if data["archived"] and not include_archived:
                    continue
                data.pop("messages")
                data.pop("conversation")
                rows.append(data)
            except (ValueError, KeyError, OSError):
                continue
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
        offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
        return {"total": len(rows), "chats": rows[offset:offset + limit],
                "next_offset": offset + limit if offset + limit < len(rows) else None,
                "keep_revisions": KEEP_REVISIONS, "keep_days": KEEP_DAYS}


class Capture:
    """Observe a copy of the actual response without modifying the live stream."""
    def __init__(self, vault, chat_id, messages, title, stream=True):
        self.vault, self.chat_id, self.title = vault, chat_id, title
        self.messages = references.normalized_messages(messages)
        self.stream, self.finished, self.enabled = stream, False, True
        self.buffer = b""
        self.content, self.reasoning, self.calls = [], [], {}
        self.bytes_seen = 0
        self.dirty = False
        initial = vault.save_fallback(chat_id, messages, title)
        self.request_revision = initial["revision"]
        self.last_checkpoint = time.monotonic()

    def observe(self, payload):
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not choices or not isinstance(choices[0], dict):
            return
        choice = choices[0]
        delta = choice.get("delta", choice.get("message", {}))
        if not isinstance(delta, dict):
            return
        if isinstance(delta.get("content"), str):
            self.content.append(delta["content"])
            self.dirty = True
        if isinstance(delta.get("reasoning_content"), str):
            self.reasoning.append(delta["reasoning_content"])
        for call in delta.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            index = call.get("index", len(self.calls))
            target = self.calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            if call.get("id"):
                target["id"] = call["id"]
                self.dirty = True
            fn = call.get("function", {})
            for key in ("name", "arguments"):
                if isinstance(fn.get(key), str):
                    target["function"][key] += fn[key]
                    self.dirty = True
        if choice.get("finish_reason"):
            self.dirty = self.dirty or not self.finished
            self.finished = True

    def feed(self, chunk):
        if not self.enabled:
            return
        self.bytes_seen += len(chunk)
        if self.bytes_seen > MAX_BODY:
            self.enabled = False
            return
        self.buffer += chunk
        if self.stream:
            self.buffer = self.buffer.replace(b"\r\n", b"\n")
            while b"\n\n" in self.buffer:
                block, self.buffer = self.buffer.split(b"\n\n", 1)
                for line in block.split(b"\n"):
                    if not line.startswith(b"data:"):
                        continue
                    value = line[5:].strip()
                    if value == b"[DONE]":
                        self.finished = True
                    else:
                        try:
                            self.observe(json.loads(value))
                        except (ValueError, TypeError, AttributeError):
                            pass
        if time.monotonic() - self.last_checkpoint >= 5:
            self.commit()

    def commit(self):
        if not self.enabled:
            return
        if not self.stream and self.buffer and not self.finished:
            try:
                self.observe(json.loads(self.buffer))
            except (ValueError, TypeError, AttributeError):
                return
        if not self.content and not self.calls:
            return
        if not self.dirty:
            return
        assistant = {"role": "assistant", "content": "".join(self.content)}
        if self.calls:
            assistant["tool_calls"] = list(self.calls.values())
        saved = self.vault.save_fallback(self.chat_id, self.messages + [assistant], self.title, self.finished,
                                         expected_revision=self.request_revision)
        self.last_checkpoint = time.monotonic()
        if saved.get("conflict"):
            self.enabled = False
        else:
            self.request_revision = saved["revision"]
        self.dirty = False
