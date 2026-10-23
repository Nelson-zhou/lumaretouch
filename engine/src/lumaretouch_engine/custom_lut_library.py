"""Local immutable content-addressed CUBE copies in a transactional SQLite library.

No external downloads, no arbitrary path in recipes, no deletion of source files.
Soft removal retains asset bytes for project/history references and undo.
"""
from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from .custom_lut_native import ParsedCube, MAX_BYTES
MAX_ASSETS = 512
MAX_TOTAL = 256 * 1024 * 1024


def digest_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("无效 LUT 内容标识")
    return value


def display_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError("LUT 名称须为 1–120 个可见字符")
    return value.strip()


class Library:
    def __init__(self, root: Path):
        # Host supplies a private app-data directory, never a path from an untrusted recipe.
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink(): raise ValueError("LUT 库目录不能是符号链接")
        db = root / "custom-luts.sqlite3"
        if db.is_symlink(): raise ValueError("LUT 库不能是符号链接")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(db, check_same_thread=False, timeout=5)
        self._db.execute("CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, name TEXT NOT NULL, content BLOB NOT NULL, removed INTEGER NOT NULL DEFAULT 0)")
        self._db.execute("CREATE TRIGGER IF NOT EXISTS immutable_content BEFORE UPDATE OF id,content ON assets BEGIN SELECT RAISE(ABORT, 'immutable LUT content'); END")
        self._db.commit()

    def close(self):
        with self._lock: self._db.close()

    def import_path(self, path, cancelled=lambda: False):
        """Host-native picker result only. Open once, forbid symlink/FIFO/device input."""
        data, name = self._read_path(path, cancelled)
        return self.import_bytes(data, name, cancelled)

    @staticmethod
    def _read_path(path, cancelled):
        path = Path(path)
        if path.suffix.lower() != ".cube": raise ValueError("请选择 .cube 文件")
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES: raise ValueError("CUBE 文件类型或大小无效")
            if cancelled(): raise InterruptedError("导入已取消")
            data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: raise ValueError("CUBE 文件在读取时超过预算")
        return data, path.stem

    def import_bytes(self, data: bytes, name: str, cancelled=lambda: False):
        name = display_name(name)
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES: raise ValueError("CUBE 文件大小无效")
        if cancelled(): raise InterruptedError("导入已取消")
        with ParsedCube(data): pass  # Strict Rust validation before any write.
        ident = hashlib.sha256(data).hexdigest()
        with self._lock, self._db:
            self._db.execute("BEGIN IMMEDIATE")
            if cancelled(): raise InterruptedError("导入已取消")
            row = self._db.execute("SELECT id FROM assets WHERE id=?", (ident,)).fetchone()
            if row:
                self._db.execute("UPDATE assets SET removed=0 WHERE id=?", (ident,))
            else:
                count, size = self._db.execute("SELECT count(*), coalesce(sum(length(content)),0) FROM assets").fetchone()
                if count >= MAX_ASSETS or size + len(data) > MAX_TOTAL:
                    raise ValueError("本地 LUT 库达到 512 项或 256 MiB 上限；保留的撤销资源也计入预算")
                self._db.execute("INSERT INTO assets(id,name,content) VALUES(?,?,?)", (ident, name, data))
            if cancelled(): raise InterruptedError("导入已取消")
        return ident

    def list(self):
        with self._lock:
            return [dict(id=r[0], name=r[1], bytes=r[2]) for r in self._db.execute("SELECT id,name,length(content) FROM assets WHERE removed=0 ORDER BY name,id")]

    def rename(self, ident, name):
        with self._lock, self._db:
            if self._db.execute("UPDATE assets SET name=? WHERE id=?", (display_name(name), digest_id(ident))).rowcount != 1: raise FileNotFoundError("LUT 资源缺失")

    def remove(self, ident):
        self._visibility(ident, 1)

    def undo_remove(self, ident):
        self._visibility(ident, 0)

    def _visibility(self, ident, removed):
        with self._lock, self._db:
            if self._db.execute("UPDATE assets SET removed=? WHERE id=?", (removed, digest_id(ident))).rowcount != 1: raise FileNotFoundError("LUT 资源缺失")

    def contains(self, ident):
        with self._lock:
            return self._db.execute("SELECT 1 FROM assets WHERE id=?", (digest_id(ident),)).fetchone() is not None

    def content(self, ident):
        ident = digest_id(ident)
        with self._lock:
            row = self._db.execute("SELECT content FROM assets WHERE id=?", (ident,)).fetchone()
        if not row: raise FileNotFoundError(f"缺少 LUT {ident}；请重新定位完全相同的 .cube 文件，或明确移除此效果")
        data = bytes(row[0])
        if hashlib.sha256(data).hexdigest() != ident: raise ValueError("LUT 副本损坏；未静默替换效果")
        return data

    def portable(self, ident):
        ident = digest_id(ident)
        data = self.content(ident)
        with self._lock: name = self._db.execute("SELECT name FROM assets WHERE id=?", (ident,)).fetchone()[0]
        return {"schema": 1, "sha256": ident, "name": name, "cube_base64": base64.b64encode(data).decode("ascii")}

    def restore(self, payload, cancelled=lambda: False):
        if not isinstance(payload, dict) or set(payload) != {"schema", "sha256", "name", "cube_base64"} or type(payload["schema"]) is not int or payload["schema"] != 1: raise ValueError("不支持的 LUT 便携资源")
        ident = digest_id(payload["sha256"])
        text = payload["cube_base64"]
        if not isinstance(text, str) or len(text) > ((MAX_BYTES+2)//3)*4: raise ValueError("LUT 便携资源超出预算")
        data = base64.b64decode(text, validate=True)
        if hashlib.sha256(data).hexdigest() != ident: raise ValueError("LUT 便携资源校验失败")
        return self.import_bytes(data, payload["name"], cancelled)

    def recover(self, ident, path, cancelled=lambda: False):
        """Recovery never silently replaces a recipe with a different LUT."""
        ident = digest_id(ident)
        data, name = self._read_path(path, cancelled)
        if hashlib.sha256(data).hexdigest() != ident: raise ValueError("所选 LUT 内容不同；当前效果未替换")
        return self.import_bytes(data, name, cancelled)


_default = None
_default_lock = threading.Lock()
def default_library():
    global _default
    with _default_lock:
        if _default is None:
            root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "lumaretouch/custom-luts"
            _default = Library(root)
        return _default
