"""预设落盘层：用户预设目录、导入的静态边界、原子写（LNX-P0-PRESET / PRESET-001、002）。

与 `scope.py` 的分工：scope 只管"预设应该长什么样、参数合不合法"（纯函数，不碰文件系统），
这里只管"从磁盘拿进来 / 写回磁盘"。分开写是因为 PRESET-002 的判据正是这两件事的交界处：
"过大资产""未知 schema""脚本内容"要在**读进来那一刻**被拒，而"不写项目外路径"要由
落盘这一层守住——两处混在一个函数里，最容易出的错就是校验用的是 A 处的规则、写入用的是
B 处的路径。

目录选择：`$XDG_DATA_HOME/LumaRetouch/presets`（缺省 `~/.local/share/…`），测试与离线自证
用 `LRT_PRESET_DIR` 覆盖。为什么不放工程文件旁边：预设是**跨项目**的用户资产（手册：
"个人预设共用"），跟着项目走会让换一个项目就"预设失踪"。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import stat
import errno
from functools import wraps
from . import preset_organisation_store as PO

def _catalogue_locked(fn):
    @wraps(fn)
    def locked(*args, **kwargs):
        with PO.catalogue_lock(kwargs.get("directory") or preset_dir()):
            return fn(*args, **kwargs)
    return locked

from .scope import (PRESET_MAX_BYTES, PRESET_SCHEMA, ScopeError, dump_preset, safe_slug,
                    validate_preset)

DIR_ENV = "LRT_PRESET_DIR"
FNAME_RE = re.compile(r"^[a-z0-9._-]{1,64}\.json$")


class PresetStorageError(ScopeError):
    def __init__(self, message, *, outcome_unknown=False, committed=False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown
        self.committed = committed


def _storage_error(error, *, committing=False, committed=False):
    definite = {errno.EACCES, errno.EPERM, errno.ENOENT, errno.ENOTDIR, errno.EISDIR,
                errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EEXIST, errno.EXDEV,
                errno.ENAMETOOLONG, errno.EMLINK}
    unknown = committed or (committing and getattr(error, "errno", None) not in definite)
    certainty = True if committed else None if unknown else False
    return PresetStorageError(str(error), outcome_unknown=unknown, committed=certainty)


def _sync_parent(path):
    if os.name == "posix":
        fd = os.open(os.path.dirname(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(fd)
        finally: os.close(fd)


def preset_dir() -> str:
    override = os.environ.get(DIR_ENV)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local",
                                                           "share")
    return os.path.join(base, "LumaRetouch", "presets")


def _path_for(preset_id: str, directory: str | None = None) -> str:
    """id → 目录里的那个文件名。slug 规则在 `safe_slug` 里，这里再兜一道：
    文件名必须整段匹配 `[a-z0-9._-]{1,64}.json`，任何别的字符（含分隔符）都拒。
    这一道不是重复劳动：`safe_slug` 管的是"用户给的名字"，这里管的是"拼出来的路径"，
    两者不一致时宁可响，也不要写到一个猜不到的位置。"""
    pid = safe_slug(preset_id)
    fname = f"{pid}.json"
    if not FNAME_RE.match(fname):
        raise ScopeError(f"预设文件名不合法：{fname!r}")
    root = os.path.abspath(directory or preset_dir())
    out = os.path.abspath(os.path.join(root, fname))
    if os.path.commonpath([out, root]) != root:
        raise ScopeError(f"预设落点跑到了目录外面：{out}（根 {root}）")
    return out


def builtin_docs() -> list[dict]:
    """随包的两个模块预设：一个"人像"、一个"色彩"。

    为什么内置写在代码里而不是 data/*.json：deb 的引擎打包只拷 `data/` 里的**权重**
    （stage-engine.sh 那一段），新加一类数据文件就要同步改打包脚本，漏改的后果是
    "装机后预设列表是空的"——而这在开发机上永远看不出来。参数是代码级事实，写在代码里
    少一条会漂的链路。

    数值都是真的参数（走真的命令、真的改像素），不是占位：人像预设只动磨皮强度那一族，
    色彩预设只动曝光/白平衡，正是 PRESET-001 要判的两类作用域。
    """
    return [
        {"schema": PRESET_SCHEMA, "id": "portrait-soft", "name": "柔肤（人像）",
         "kind": "portrait", "author": "LumaRetouch",
         "note": "只作用人像模块：磨皮强度 0.45。色彩、裁剪、曝光一律不碰。",
         "modules": {"lnx.skin.v1": {"strength": 0.45},
                     "lnx.blemish.v1": {"strength": 0.45}}},
        {"schema": PRESET_SCHEMA, "id": "color-warm", "name": "暖调（色彩）",
         "kind": "color", "author": "LumaRetouch",
         "note": "只作用色彩模块：+0.30 EV、色温 +250 K、色调 +0.05。人像与裁剪不碰。",
         "modules": {"lnx.exposure.v1": {"ev": 0.30},
                     "lnx.white_balance.v1": {"temperature_shift": 250.0, "tint_shift": 0.05}}},
    ]


def builtin_ids() -> tuple[str, ...]:
    """内置预设的 id 名单（`builtin` 不写进字面里：它是“从哪个目录读到的”这个事实，
    不是文件内容，所以由引擎按目录注进去，见 scope.validate_preset 的第⑥条）。"""
    return tuple(b["id"] for b in builtin_docs())


def load_file(path: str, *, max_bytes: int = PRESET_MAX_BYTES) -> dict:
    """读一个预设文件：过大 / 非 JSON / 对象形状不对 / schema 不认识，全部整条拒。

    体积上限在**打开文件之前**用 stat 判一次、读完再判一次：前者防"拿一个 8 GB 的
    文件当预设"（一次 read 就能把内存打满），后者防 stat 与实读之间文件被换掉。
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError as error:
        raise ScopeError(f"预设文件不存在：{path}") from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise ScopeError("预设必须是普通文件")
        if info.st_size > max_bytes:
            raise ScopeError(f"预设文件过大（{info.st_size} > {max_bytes} 字节）：这不是参数文件")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            raw = fh.read(max_bytes + 1)
    finally:
        os.close(fd)
    if len(raw) > max_bytes:
        raise ScopeError(f"预设文件过大（实读 {len(raw)} > {max_bytes} 字节）")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ScopeError(f"预设不是 UTF-8 文本：{e}") from None
    if text.startswith("#!") or text.startswith("<?php") or "<script" in text.lower():
        # 只做"看起来是可执行内容"的显式拒绝：引擎永远不会执行预设里的东西，
        # 但把这类文件接进预设列表会让用户以为它有用。
        raise ScopeError("预设文件里出现了脚本/可执行内容：预设只是参数，引擎不执行任何内容")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise ScopeError(f"预设不是合法 JSON：{e}") from None
    return validate_preset(doc)


@_catalogue_locked
def raw_list_all() -> tuple[list[dict], list[dict]]:
    """(内置 + 用户预设, 读不了的那一些及原因)。坏掉的预设**不会被静默跳过**：
    它带着原因进 `errors`（调用方在列表事件里上报），因为“我导入的预设怎么不见了”
    必须有答案。"""
    out = [validate_preset(d, builtin=True) for d in builtin_docs()]
    errors: list[dict] = []
    root = preset_dir()
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            if not name.endswith(".json"):
                continue
            full = os.path.join(root, name)
            try:
                doc = load_file(full)
            except ScopeError as e:
                errors.append({"file": full, "error": str(e)})
                continue
            if any(o["id"] == doc["id"] and o["builtin"] for o in out):
                errors.append({"file": full, "error": f"内置预设 {doc['id']} 不能被用户文件顶掉"})
                continue
            out.append(doc)
    return out, errors


@_catalogue_locked
def list_all() -> tuple[list[dict], list[dict]]:
    raw, errors = raw_list_all()
    return PO.overlay(raw, preset_dir()), errors

def docs() -> list[dict]:
    """只要列表、不要错误（给枚举、报表用）。"""
    return list_all()[0]


@_catalogue_locked
def save(doc: dict, *, force: bool = False, directory: str | None = None) -> str:
    # `builtin` 是派生字段（上面的 validate 不允文件里带它），而落盘层的这一写永远进
    # 用户目录——用户目录里不存在“内置”这回事。剔掉后再校一次，这样“已校验副本回炉”
    # 与“新文档”两条路都能走，而且不会因一个无意义键碎在第二遍校验上。
    clean = validate_preset({k: v for k, v in doc.items() if k != "builtin"})
    if clean["id"] in builtin_ids():
        raise ScopeError(f"预设 id 与内置预设 {clean['id']} 相撞：用户文件不能顶掉随包分发的那一个"
                         "（列表里同 id 会被报成错误，而不是静默二选一）")
    root = directory or preset_dir()
    metadata = PO.load(root)['items'].get(clean['id'])
    if metadata and metadata['deleted']:
        raise ScopeError('同 ID 预设仍在回收站；请先恢复，或导入为新副本')
    if metadata and metadata['name'] is not None and metadata['name'] != clean['name']:
        raise ScopeError('已有分类名称覆盖；请使用重命名或导入为新副本，未改写预设')
    path = _path_for(clean["id"], directory)
    if os.path.exists(path) and not force:
        raise ScopeError(f"预设 {clean['id']} 已存在（{path}）：要覆盖请显式给 force")
    # 写下去的那一份不带 `builtin`：它是派生字段，写进文件就会被读回来时当作
    # “文件自报内置”而拒——自己写的文件自己读不了，这一类“写的与读的不是一套”
    # 本轮就是在写完后跑了一次 round-trip 才响出来的。
    payload = {k: v for k, v in clean.items() if k != "builtin"}
    tmp = None; committing = False; committed = False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path),
                                         prefix=f".{clean['id']}.", suffix=".tmp", delete=False) as fh:
            tmp = fh.name
            fh.write(dump_preset(payload))
            fh.flush()
            os.fsync(fh.fileno())
        committing = True
        if force:
            os.replace(tmp, path)
        else:
            # POSIX link atomically fails if the destination appeared since our
            # precheck. Never replace a concurrently-created preset without force.
            try:
                os.link(tmp, path)
            except FileExistsError as error:
                raise ScopeError(f"预设 {clean['id']} 已存在，未覆盖：{path}") from error
        committed = True
        _sync_parent(path)
    except (OSError, UnicodeError) as error:
        raise _storage_error(error, committing=committing, committed=committed) from error
    finally:
        if tmp is not None:
            try: os.unlink(tmp)
            except OSError: pass  # A committed file is not a failed save because cleanup failed.
    return path


@_catalogue_locked
def delete(preset_id: str, *, directory: str | None = None) -> str:
    """Compatibility entrypoint: recoverable catalogue trash, never unlink a recipe."""
    if directory is not None and os.path.abspath(directory) != os.path.abspath(preset_dir()):
        raise ScopeError('回收站只支持当前预设目录')
    if preset_id in builtin_ids(): raise ScopeError('内置预设不能删除')
    store = PO.OrganisationStore(preset_dir(), raw_list_all)
    current = store.snapshot()
    store.transact({'action':'preset_trash','id':preset_id,'request_id':str(__import__('uuid').uuid4()),
                    'expected_revision':current['revision']})
    return _path_for(preset_id, directory)


def find(preset_id: str) -> dict:
    for d in docs():
        if d["id"] == preset_id:
            return d
    raise ScopeError(f"没有预设 {preset_id!r}（可用："
                     f"{', '.join(d['id'] for d in docs()) or '无'}）")
