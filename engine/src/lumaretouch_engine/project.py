"""项目持久化（LNX-P0-PROJECT；验收 CORE-001 / CORE-007 / CORE-008）。

一份项目 = 一个 JSON 文件。为什么不是 SQLite：

* CORE-008 要求"事务执行中注入进程终止，重开后恢复到**完整旧版本或完整新版本**，
  没有半个配方或损坏数据库"。同一文件系统上的 `os.replace` 是原子的：崩溃点只可能
  留下旧文件或新文件，不存在第三种。SQLite 要给同样的保证得管 journal/WAL、锁与
  损坏恢复，那是多出来的依赖与多出来的可失败面。
* 写的频率是"每次保存一次"，不是"每秒一千次事务"——数据库引擎在这里是纯成本。
* 依赖最干净：零新依赖，纯开源；出问题的时候人能直接 `cat` 那个文件。离线普惠产品
  的自检门槛应当是"看得见的字节"，不是"需要一个客户端才读得懂的库"。
* 便携：项目文件跟着照片走，拷走就是整个工程。

代价也写清楚（这是本层存在的另一个理由）：整份文档在内存里编一次 JSON，因此
**项目不适合大到几百张带自定义调色表**。上限写死在 `MAX_*` 常量里，超限的资产
不当场崩、也不假装存进去了，而是**丢弃并在 `dropped` 里逐条记原因**——"未接通
显式禁用并说明原因"这条产品纪律同样适用于持久层。

配方里那些活着的张量（消除笔/修容的画笔覆盖度、换底掩膜、调色表原件）不是 JSON：
`encode()` 把它们变成内容寻址的资产（sha256 去重：二十张图共用一张表，文件里只有
一份），认不出的类型当场记进 `dropped` 而不是静默消失。
修补记录例外：笔迹、来源坐标或算法版本缺一项都会改变成片，必须整份拒绝，不能丢弃后继续。
"""
from __future__ import annotations

import base64
import copy
from . import white_balance_recipe as WB
import dataclasses
import hashlib
import io
import json
import math
import os
import sys
import time
import uuid

import numpy as np
from .reference_color_project import validate_records as validate_reference
from .semantic_colour_project import validate_records as validate_semantic_colour
from .body_pose_project import validate_records as validate_body_pose
from .repair_record import RepairOp, check_repair_fields, validate_repair_ops
from . import virtual_copy_storage as VC

LEGACY_SCHEMA = "lrt.project.v1"
WB_SCHEMA = "lrt.project.v2"
REPAIR_SCHEMA = "lrt.project.v3"
MASK_SCHEMA = "lrt.project.v4"
GRADE_SCHEMA = "lrt.project.v5"
RECOVERY_SCHEMA = "lrt.project.v6"
MANUAL_SCHEMA = "lrt.project.v7"
STUDIO_SCHEMA = "lrt.project.v8"
OPTICS_SCHEMA = "lrt.project.v9"
SKY_SCHEMA = "lrt.project.v10"
SEMANTIC_SKY_SCHEMA = "lrt.project.v11"
SEMANTIC_COLOUR_SCHEMA = "lrt.project.v12"
BODY_SCHEMA = "lrt.project.v13"
HAIR_SCHEMA = "lrt.project.v14"
CUBE_SCHEMA = "lrt.project.v15"
TONE_SCHEMA = "lrt.project.v16"
GRADING_SCHEMA = "lrt.project.v17"
SELECTIVE_SCHEMA = "lrt.project.v18"
PRIMARY_SCHEMA = "lrt.project.v19"
DETAIL_SCHEMA = "lrt.project.v20"
GRAIN_SCHEMA = "lrt.project.v21"
COLOUR_EDITOR_SCHEMA = "lrt.project.v22"
SCHEMA = "lrt.project.v23"
SUFFIX = ".lrproject.json"

# 上限：宁可显式丢弃，也不要"保存成功但下次打开少了一半配方"这种事
MAX_ASSET_BYTES = 8_000_000          # 单个资产原始字节上限
MAX_PROJECT_BYTES = 256_000_000      # 整份文件上限：再大就不是工程，是照片备份
HASH_PREVIEW_BYTES = 4_096           # 快速指纹读的头部字节（重定位用的粗筛）

__all__ = ["ProjectError", "SCHEMA", "SUFFIX", "new_project", "load", "save",
           "encode", "decode", "fingerprint", "verify_fingerprint", "add_doc",
           "find_doc", "set_trashed", "set_tags", "put_active_version",
           "active_recipe", "project_path_for", "missing_sources"]


class ProjectError(ValueError):
    """项目文件读写与校验的错。刻意继承 ValueError：命令面那侧的守卫
    （`except (ValueError, ...)`）本来就吃它，不需要为持久层再开一条臂。"""


# ---------------------------------------------------------------- 原子落盘
def _fsync_dir(path: str) -> None:
    """把目录项也刷下去。只 fsync 文件本身，掉电后那个新名字可能还没进目录——
    于是"完整新版本"变成"文件不见了，旧版本也被替换掉了"。"""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(project: dict, path: str) -> dict:
    """原子写：临时文件 → flush+fsync → os.replace → 目录 fsync。

    返回可验事实（字节数与整份文件的 sha256）：`project_saved` 事件要报的是
    "写下去的是这一份"，而不是"我调过一次 write"。
    """
    path = os.path.abspath(str(path))
    validate(project)
    body = _migrate(project)
    body["updated_ns"] = int(time.time_ns())
    # 每次保存都重新盖写手戳：记的是“最后一次写下它的环境”，不是“创建时的环境”。
    # 只创一次的话，一份被三个版本轮流编辑的工程会拿最早那一个冒充自己。
    body["writer"] = writer_stamp()
    try:
        data = json.dumps(body, ensure_ascii=False, indent=1,
                          allow_nan=False).encode("utf-8")
    except ValueError as e:
        # allow_nan=False 是这条路的守门人：默认会把 NaN 写成 `NaN` 这种
        # 非法 JSON 字面量，当场能编出来、下次加载才炸——那正是"半个配方"的形状
        raise ProjectError(f"项目里有不能写进 JSON 的数（NaN/Inf 不接受）：{e}") from e
    if len(data) > MAX_PROJECT_BYTES:
        raise ProjectError(f"项目 {len(data)} 字节超过上限 {MAX_PROJECT_BYTES}："
                           f"这一版不把工程当照片备份，请拆项目或减少自定义调色表")
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    t0 = time.monotonic_ns()
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)             # 同一目录 ⇒ 同一文件系统 ⇒ 原子
        _fsync_dir(d)
    except Exception:
        # 半途失败不许在工程目录里留下 `.xxx.tmp`：那些文件的开头是个点，
        # 用户在文件管理器里看不见，但它们占空间、而其中一份写着“半个配方”
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"path": path, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "write_ms": round((time.monotonic_ns() - t0) / 1e6, 2),
            "updated_ns": body["updated_ns"]}


def load(path: str) -> dict:
    path = os.path.abspath(str(path))
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ProjectError(f"项目打不开：{e}") from e
    try:
        p = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        # 半截文件在这里只会以"读不出 JSON"出现——那正是 CORE-008 要区分的情形，
        # 报错必须说清是格式问题，而不是笼统一句"打不开"
        raise ProjectError(f"项目文件损坏或不是本机写过的格式（{type(e).__name__}）：{e}") from e
    validate(p)
    p = _migrate(p)
    p["_source_path"] = path
    p["_source_sha256"] = hashlib.sha256(raw).hexdigest()
    return p


def validate(p: object) -> None:
    """结构校验：不认识就拒，不要"看起来像就往下走"。

    往下的每一步都假定 docs/assets 的形状；把校验做成一段段宽容的 getattr，
    损坏文件就会变成"打开成功但少了几张图"——那比打开失败难查十倍。
    """
    if not isinstance(p, dict):
        raise ProjectError(f"项目顶层不是对象：{type(p).__name__}")
    from .people_project import validate_records as validate_people
    try: validate_people(p)
    except (ValueError,TypeError,KeyError) as error: raise ProjectError(str(error)) from error
    from .managed_import_project import validate as validate_managed_import
    try: validate_managed_import(p)
    except (ValueError,TypeError,KeyError,AttributeError) as error: raise ProjectError(str(error)) from error
    sv = p.get("schema_version")
    from .primary_calibration_adapters import validate_records as validate_primary
    try:validate_primary(p,allowed=sv in (PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except (ValueError,TypeError,KeyError,RuntimeError,OSError) as error:raise ProjectError(str(error)) from error
    from .selective_colour_adapters import validate_records as validate_selective
    try:validate_selective(p,allowed=sv in (SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except (ValueError,TypeError,KeyError) as error:raise ProjectError(str(error)) from error
    from .colour_grading_adapters import validate_records as validate_grading
    try:validate_grading(p,allowed=sv in (GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except (ValueError,TypeError,KeyError) as error:raise ProjectError(str(error)) from error
    from .colour_editor_adapters import validate_records as validate_editor
    try:validate_editor(p,allowed=sv in (COLOUR_EDITOR_SCHEMA, SCHEMA))
    except ValueError as error:raise ProjectError(str(error)) from error
    from .photo_grain_adapters import validate_records as validate_grain
    try:validate_grain(p,allowed=sv in (GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except ValueError as error:raise ProjectError(str(error)) from error
    from .photo_detail_project import validate_records as validate_photo_detail
    try:validate_photo_detail(p,allowed=sv in (DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except ValueError as error:raise ProjectError(str(error)) from error
    from .extended_tone_project import validate_records as validate_extended_tone
    try:validate_extended_tone(p,allowed=sv in (TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA))
    except (ValueError,TypeError,KeyError) as error:raise ProjectError(str(error)) from error
    from .hair_colour_project import validate as validate_hair
    try:validate_hair(p,allowed=(sv in (HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
    except (ValueError,TypeError,KeyError) as error:raise ProjectError(str(error)) from error
    try:validate_body_pose(p,allowed=(sv in (BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
    except (ValueError,TypeError,KeyError) as error:raise ProjectError(str(error)) from error
    if sv not in (LEGACY_SCHEMA, WB_SCHEMA, REPAIR_SCHEMA, MASK_SCHEMA, GRADE_SCHEMA, RECOVERY_SCHEMA, MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA):
        raise ProjectError(f"项目 schema_version={sv!r}，本版本认 {SCHEMA!r}")
    for k in ("project_id", "name", "docs", "assets"):
        if k not in p:
            raise ProjectError(f"项目缺顶层键 {k!r}")
    if not isinstance(p["docs"], list) or not isinstance(p["assets"], dict):
        raise ProjectError("项目的 docs/assets 形状不对（应为 list / dict）")
    if sv == SCHEMA:
        try:
            VC.validate_identity(p)
        except (ValueError, TypeError, KeyError) as error:
            raise ProjectError(f"Invalid virtual-copy identity: {error}") from error
    seen = set()
    for i, row in enumerate(p["docs"]):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ProjectError(f"docs[{i}] 缺 path 或形状不对")
        from .canvas_guides import validate_row as validate_guides
        try:
            validate_guides(row)
        except (ValueError, TypeError, KeyError) as error:
            raise ProjectError(f'Invalid canvas guides for docs[{i}]: {error}') from error
        rp = row["path"]
        if rp in seen and sv != SCHEMA:
            raise ProjectError(f"docs[{i}] 的 path 与前面重复：{rp}")
        seen.add(rp)
        if not isinstance(row.get("versions"), list):
            raise ProjectError(f"docs[{i}] 的 versions 不是列表")
        # 活动版本是配方的一部分：缺了这个键就不知道打开哪一版。这里只校形状，
        # “指向不存在的版本”那一格在 `active_recipe()` 里逐张响：一张图坏了不该把
        # 整个工程里几百张图一起锁在外面
        if "active_version" not in row:
            raise ProjectError(f"docs[{i}] 缺 active_version")


        for version in row["versions"]:
            if not isinstance(version, dict):
                raise ProjectError("Project version must be an object")
            recipe = version.get("recipe")
            if recipe is not None:
                try:
                    WB.normalize_state(recipe, required=(sv != LEGACY_SCHEMA))
                except ValueError as error:
                    raise ProjectError(f"Invalid white-balance recipe: {error}") from error
                if sv in (MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA):
                    _check_manual_liquify_record(recipe.get("_manual_liquify"))
        from .sky_replacement_project import validate_records as validate_sky
        try: validate_sky(row,required=(sv in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),allowed=(sv in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),semantic=(sv in (SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
        except ValueError as error: raise ProjectError(str(error)) from error
        from .brow_shape_project import validate_records as validate_brows
        from .nose_shape_project import validate_records as validate_noses
        from .eye_shape_project import validate_records as validate_eyes
        from .mouth_shape_project import validate_records as validate_mouth
        from .lip_makeup_project import validate_records as validate_lips
        try: validate_lips(row); validate_brows(row); validate_noses(row); validate_eyes(row); validate_mouth(row); validate_reference(row); validate_semantic_colour(row,allowed=(sv in (SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)),assets=p["assets"]); validate_body_pose(row,allowed=(sv in (BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
        except ValueError as error: raise ProjectError(str(error)) from error
        from .optics_project import validate_records as validate_optics
        try: validate_optics(row,required=(sv in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)),allowed=(sv in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
        except ValueError as error: raise ProjectError(str(error)) from error
        from .id_background_project import validate_records as validate_id_background
        try: validate_id_background(row, assets=p['assets'])
        except ValueError as error: raise ProjectError(str(error)) from error
        from .studio_background_project import validate_records as validate_studio
        try: validate_studio(row, required=(sv in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)), allowed=(sv in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
        except ValueError as error: raise ProjectError(str(error)) from error
        # Check the complete owned row, not only its active recipe: inactive
        # versions, document snapshots and nested history must fail together.
        _validate_encoded_repairs(row, p["assets"],
            allow_legacy=(sv in (LEGACY_SCHEMA, WB_SCHEMA)),
            allow_local_grades=(sv in (GRADE_SCHEMA, RECOVERY_SCHEMA, MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),
            allow_effect_recovery=(sv in (RECOVERY_SCHEMA, MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),
            require_manual_liquify=(sv in (MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)))


def _migrate(project):
    """Own nested versions; preserve legacy pixels and record explicit heal kinds."""
    result = copy.deepcopy(project)
    previous = result["schema_version"]
    if previous not in (COLOUR_EDITOR_SCHEMA, SCHEMA):
        from .manual_liquify_state import migrate_legacy_states as migrate_manual
        from .studio_background_state import migrate_legacy_states as migrate_studio
        from .optics_state import migrate_legacy_states as migrate_optics
        from .sky_replacement_state import migrate_legacy_states as migrate_sky
        from .semantic_colour_project import migrate as migrate_semantic_colour
        from .body_pose_project import migrate as migrate_body_pose
        for row in result["docs"]:
            # Include document snapshots and inactive/nested history states, not
            # just the selected version. Existing manual records are never erased.
            migrate_manual(row)
            migrate_studio(row)
            migrate_optics(row)
            migrate_sky(row)
            migrate_semantic_colour(row); migrate_body_pose(row)
            for version in row["versions"]:
                if version.get("recipe") is not None:
                    version["recipe"] = WB.normalize_state(version["recipe"])
                    if previous in (LEGACY_SCHEMA, WB_SCHEMA):
                        _migrate_repair_kinds(version["recipe"])
                    if previous in (LEGACY_SCHEMA, WB_SCHEMA, REPAIR_SCHEMA, MASK_SCHEMA):
                        _migrate_local_grade_states(version["recipe"], root=True)
                    if previous in (LEGACY_SCHEMA, WB_SCHEMA, REPAIR_SCHEMA, MASK_SCHEMA, GRADE_SCHEMA):
                        from .effect_recovery_state import migrate_legacy_states
                        migrate_legacy_states(version["recipe"], root=True)
                    migrate_manual(version["recipe"], root=True)
                    migrate_studio(version["recipe"], root=True)
                    migrate_optics(version["recipe"], root=True)
                    migrate_sky(version["recipe"], root=True)
                    migrate_semantic_colour(version["recipe"],root=True); migrate_body_pose(version["recipe"],root=True)
        result["schema_version"] = SCHEMA
        result.setdefault("migration_notes", []).append(
            f"Migrated {previous} to v16: legacy white balance retained; only v1/v2 missing repair kinds migrate to heal. "
            "Existing scalar grades and composed masks keep their exact order; v5 independent grade groups and v7 manual liquify are preserved. Studio background starts neutral only where absent. New post-manual optics starts exactly neutral where absent; old operators are not reordered. "
            "Only v1-v4 independent groups start empty; only pre-v6 effect recovery starts empty. "
            "Existing v6 recovery is preserved. Manual liquify starts empty only where absent in v1-v6. "
            "Sky replacement starts neutral only where absent; v10 preserves original source/asset bindings and explicit region vectors. "
            "v16 adds independent extended tone and original monochrome output mode where explicitly saved; absent recipes stay neutral. v15 adds lossless custom CUBE assets; v14 retains source-owned hair support and lossless semantic evidence; absent hair intent remains neutral. v13 body bank ownership is preserved. "
            "v11 sky semantics are preserved. v12 adds a separate neutral semantic-colour group only where absent; retained masks use their own rendered-canvas domain. "
            "v13 adds source-owned body operation banks without widening shoulder reviews to other anatomy. Readers older than v13 must reject rather than silently drop body edits; v12 semantic colour and v11 sky ownership remain unchanged.")
    if previous != SCHEMA:
        try:
            VC.ensure_identity(result)
        except (ValueError, TypeError, KeyError) as error:
            raise ProjectError(f"Cannot migrate document identity: {error}") from error
        result["schema_version"] = SCHEMA
        result.setdefault("migration_notes", []).append(
            f"Migrated {previous} to v23: stable logical document/source/recipe identities; "
            "legacy recipes and provenance are unchanged. Independent sources are not deduplicated.")
        validate(result)
    return result


_REPAIR_STACKS = frozenset(("_repair_ops", "_redo_ops", "repair_ops", "redo_ops"))


def _repair_weight(ref, assets):
    """Repair coverage is required data, not a best-effort generic asset."""
    try:
        if (type(ref) is not dict or set(ref) - {"__asset__", "at"}
                or ("at" in ref and type(ref["at"]) is not str)):
            raise ValueError("Repair coverage must reference an asset")
        key = ref.get("__asset__")
        if (type(key) is not str or len(key) != 71 or not key.startswith("sha256:")
                or any(c not in "0123456789abcdef" for c in key[7:])):
            raise ValueError("Invalid repair coverage asset reference")
        asset = assets.get(key)
        if type(asset) is not dict or set(asset) != {"kind", "shape", "dtype", "bytes", "b64"}:
            raise ValueError("Missing repair coverage asset")
        shape = asset.get("shape")
        if (not isinstance(shape, list) or len(shape) != 2
                or any(type(v) is not int or v < 1 for v in shape)
                or shape[0] * shape[1] > 100_000_000
                or asset.get("dtype") != "uint8"):
            raise ValueError("Repair coverage asset must be bounded (H,W) uint8")
        size, encoded = asset.get("bytes"), asset.get("b64")
        if (type(size) is not int or not 0 <= size <= MAX_ASSET_BYTES
                or type(encoded) is not str or len(encoded) > ((MAX_ASSET_BYTES + 2) // 3) * 4):
            raise ValueError("Repair coverage asset exceeds its byte budget")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != key[7:]:
            raise ValueError("Repair coverage asset length/hash mismatch")
        if asset.get("kind") == "raw":
            return np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()
        if asset.get("kind") != "png":
            raise ValueError("Unsupported repair coverage asset encoding")
        # Check the actual dimensions before Pillow can allocate/decompress a
        # forged PNG whose tiny metadata shape conceals an enormous raster.
        if (len(raw) < 29 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR"
                or int.from_bytes(raw[16:20], "big") != shape[1]
                or int.from_bytes(raw[20:24], "big") != shape[0]
                or raw[24:26] != b"\x08\x00"):
            raise ValueError("Repair PNG header does not match its exact shape/type")
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != "PNG" or im.mode != "L" or im.size != (shape[1], shape[0]):
                raise ValueError("Repair PNG asset does not match its exact shape/type")
            return np.array(im, dtype=np.uint8, copy=True)
    except (ValueError, TypeError, KeyError, OSError) as error:
        raise ProjectError(f"Invalid repair coverage asset: {error}") from error


def _repair_fields(value, assets, *, allow_legacy=True, shape=None):
    if (type(value) is not dict or set(value) != {"__dc__", "fields"}
            or value.get("__dc__") != "RepairOp" or type(value.get("fields")) is not dict):
        raise ProjectError("Repair stack contains an unknown or malformed RepairOp")
    fields = dict(value["fields"])
    # Validate kind/params and exact field names before reading any large asset.
    required = {"op_id", "weight", "params"}
    if not required <= set(fields) or set(fields) - (required | {"kind"}):
        raise ProjectError("Invalid RepairOp fields")
    from .repair_record import check_repair_params
    try:
        if not allow_legacy and "kind" not in fields:
            raise ValueError("RepairOp kind is required in project v3")
        check_repair_params(fields.get("kind", "heal"), fields["params"])
        fields["weight"] = _repair_weight(fields["weight"], assets)
        return check_repair_fields(fields, shape=shape, allow_legacy=allow_legacy)
    except ValueError as error:
        raise ProjectError(f"Invalid RepairOp: {error}") from error


def _validate_encoded_repairs(value, assets, *, allow_legacy, allow_local_grades=True,
                              allow_effect_recovery=True, require_manual_liquify=False):
    """Check every saved version, including inactive versions and redo stacks."""
    if isinstance(value, dict):
        if "_manual_liquify" in value:
            _check_manual_liquify_record(value["_manual_liquify"])
        elif require_manual_liquify and any(key in value for key in
                ("_strength", "_grade", "_grade_scope", "_local_masks",
                 "_local_grade_layers", "_effect_recovery")):
            raise ProjectError("Project v7 document/history state is missing manual liquify intent")
        if "_local_masks" in value:
            from .local_mask_state import check
            check(value["_local_masks"])
        if "_local_grade_layers" in value:
            if not allow_local_grades:
                raise ProjectError('Independent local grades cannot be stored under a pre-v5 schema')
            _check_local_grade_record(value['_local_grade_layers'])
        if '_effect_recovery' in value:
            if not allow_effect_recovery:
                raise ProjectError('Effect recovery cannot be stored under a pre-v6 schema')
            _check_effect_recovery_record(value['_effect_recovery'])
        if value.get("__dc__") == "RepairOp":
            _repair_fields(value, assets, allow_legacy=allow_legacy)
            return
        for key, child in value.items():
            if key in _REPAIR_STACKS:
                if type(child) is not list:
                    raise ProjectError(f"Repair stack {key} must be a list")
                shape = value.get("_proxy")
                if shape is not None and (not isinstance(shape, (list, tuple)) or len(shape) != 2
                        or any(type(n) is not int or n < 1 for n in shape)):
                    raise ProjectError("Invalid repair proxy dimensions")
                for record in child:
                    _repair_fields(record, assets, allow_legacy=allow_legacy, shape=shape)
            else:
                _validate_encoded_repairs(child, assets, allow_legacy=allow_legacy,
                                          allow_local_grades=allow_local_grades,
                                          allow_effect_recovery=allow_effect_recovery,
                                          require_manual_liquify=require_manual_liquify)
    elif isinstance(value, list):
        for child in value:
            _validate_encoded_repairs(child, assets, allow_legacy=allow_legacy,
                                      allow_local_grades=allow_local_grades,
                                      allow_effect_recovery=allow_effect_recovery,
                                      require_manual_liquify=require_manual_liquify)


def _check_manual_liquify_record(value):
    from .manual_liquify_state import check_saved_record
    try:
        check_saved_record(value)
    except ValueError as error:
        raise ProjectError(f"Invalid manual-liquify recipe: {error}") from error


def _check_effect_recovery_record(value):
    from .effect_recovery_state import check_saved_record
    try:
        check_saved_record(value)
    except ValueError as error:
        raise ProjectError(f'Invalid effect-recovery recipe: {error}') from error


def _check_local_grade_record(value):
    from .local_grade_layers import check
    try:
        # Missing old state defaults to empty at replay, but an explicitly saved
        # null must not silently erase the intent of a v5 group record.
        if type(value) is not dict:
            raise ValueError('Retained local-grade record must be an object')
        check(value)
    except ValueError as error:
        raise ProjectError(f'Invalid independent local-grade recipe: {error}') from error


def _migrate_local_grade_states(value, *, root=False):
    """Add only empty layers to every legacy document/history state, owned copy."""
    if isinstance(value, dict):
        for child in list(value.values()):
            _migrate_local_grade_states(child)
        if root or any(key in value for key in ('_grade', '_grade_scope', '_local_masks')):
            from .local_grade_layers import empty
            value['_local_grade_layers'] = empty()
    elif isinstance(value, list):
        for child in value:
            _migrate_local_grade_states(child)


def _migrate_repair_kinds(value):
    if isinstance(value, dict):
        if value.get("__dc__") == "RepairOp":
            value["fields"].setdefault("kind", "heal")
        else:
            for child in value.values():
                _migrate_repair_kinds(child)
    elif isinstance(value, list):
        for child in value:
            _migrate_repair_kinds(child)


# ---------------------------------------------------------------- 指纹
def fingerprint(path: str, *, full: bool = False) -> dict:
    """文件指纹。`hash_level` 说清手里的是哪一等，不把两等混成一个数。

    full=True：整文件 sha256。CORE-001 的"源文件哈希不变"要的是这一等。
    full=False：只读头部 HASH_PREVIEW_BYTES + 长度 + mtime。扫描 512 张时逐张
    全文件哈希会把导入拖成几十秒（本机 0.41 MB 量到 warm 1.0 ms、0.03 MB 合成
    DNG 0.2 ms，≈ 2.4 ms/MB；25 MB 真机 DNG 按这一条推是 ≈ 60 ms——本仓没有
    25 MB 样张，所以这里明写哪个是量出来的、哪个是推出来的），而导入那一层只要
    能认出"文件变了/被换了"。重开与显式核对才升级到 full。

    两等都只在导入与显式核对时做，逐帧路径一次都不做。
    """
    head = bytearray()
    n = 0
    h_full = hashlib.sha256() if full else None
    with open(path, "rb") as f:            # 只读：这里写一个 w 就能顶掉 CORE-001
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            n += len(b)
            if h_full is not None:
                h_full.update(b)
            if len(head) < HASH_PREVIEW_BYTES:
                head += b[:HASH_PREVIEW_BYTES - len(head)]
    st = os.stat(path)
    return {"path": os.path.abspath(path), "bytes": n,
            "sha256": h_full.hexdigest() if h_full is not None else None,
            "head_sha256": hashlib.sha256(bytes(head)).hexdigest(),
            "hash_level": "full" if full else "head",
            "mtime_ns": int(st.st_mtime_ns), "readonly": not os.access(path, os.W_OK)}


def verify_fingerprint(path: str, fp: dict) -> dict:
    """重开时对一遍指纹。缺 / 长度变 / 头部变 分开报：处置不一样。

    缺文件是“在哪”；长度变了是“这张图被动过”；只有 mtime 变了而字节没变，
    是拷贝/同步工具干的，不该报成“照片坏了”。
    """
    exists = os.path.isfile(path)
    out = {"path": path, "exists": exists, "level": fp.get("hash_level", "head"),
           "bytes_match": False, "head_match": False, "full_match": None}
    if not exists:
        return out
    now = fingerprint(path, full=fp.get("hash_level") == "full")
    out["bytes_match"] = now["bytes"] == fp.get("bytes")
    out["head_match"] = now["head_sha256"] == fp.get("head_sha256")
    if fp.get("sha256"):
        out["full_match"] = now["sha256"] == fp["sha256"]
    out["mtime_moved_only"] = bool(out["head_match"] and out["bytes_match"]
                                   and now["mtime_ns"] != fp.get("mtime_ns"))
    return out


# ---------------------------------------------------------------- 编解码
def _png_mode(arr: np.ndarray) -> str | None:
    """能无损走 PNG 的 uint8 形状：“掩膜/覆盖度”那一族。

    (H,W) → L；(H,W,1) 也是单通道（上一版把它当 RGB 递，Pillow 直接报
    “Cannot handle this data type”，而画笔覆盖度就是这一形状）；
    (H,W,3)/(H,W,4) → RGB/RGBA。其余形状回退 raw：不是为了支持更多形状，
    而是为了“存进去的字节与读回来的字节同一个布道”不能靠通道拼装猜。
    """
    if arr.dtype != np.uint8 or arr.ndim not in (2, 3) or 0 in arr.shape:
        return None
    if arr.ndim == 2:
        return "L"
    return {1: "L", 3: "RGB", 4: "RGBA"}.get(int(arr.shape[2]))


def _png_bytes(arr: np.ndarray) -> bytes:
    from PIL import Image

    mode = _png_mode(arr)
    a = arr if arr.ndim == 2 else arr[:, :, 0] if mode == "L" else arr[:, :, :3] \
        if mode == "RGB" else arr
    im = Image.fromarray(np.ascontiguousarray(a), mode)
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6)   # 无损：这里省的是体积，不是位深
    return buf.getvalue()


def _from_png_bytes(raw: bytes, shape: list[int]) -> np.ndarray:
    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    a = np.asarray(im)
    # 形状以资产里记的那份为准：PNG 只保证像素，不保证通道维的个数。
    # 尺寸乘不上就是“记的形状与字节不符”（文件被改过），报给调用方而不是拼一个看着像的
    if a.shape != tuple(shape):
        a = a.reshape(shape) if a.size == int(np.prod(shape)) else None
        if a is None:
            raise ValueError(f"PNG 资产与记录形状 {shape} 对不上")
    return a


def encode(value: object, assets: dict, dropped: list, at: str) -> object:
    """递归转成 JSON 安全值。不认识的东西**必须留话**，不能静静消失。"""
    from .custom_lut_asset import CustomCube
    if isinstance(value, CustomCube):
        ref = _encode_blob(value.content, assets, [], at, kind="custom-cube")
        return {"__custom_cube__": 1, "asset": ref, "sha256": value.asset_id, "name": value.title}
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            dropped.append({"at": at, "reason": f"非有限浮点 {value!r}，JSON 不表示它"})
            return None
        return value
    if isinstance(value, np.ndarray):
        return _encode_array(value, assets, dropped, at)
    if isinstance(value, (bytes, bytearray)):
        return _encode_blob(bytes(value), assets, dropped, at, kind="bytes")
    if type(value) is RepairOp:
        try:
            clean = check_repair_fields(vars(value), allow_legacy=False)
        except ValueError as error:
            raise ProjectError(f"Invalid RepairOp: {error}") from error
        failed = []
        encoded = {k: encode(v, assets, failed, f"{at}.{k}") for k, v in clean.items()}
        if failed:
            raise ProjectError(f"RepairOp cannot be saved without data loss: {failed}")
        return {"__dc__": "RepairOp", "fields": encoded}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"__dc__": type(value).__name__,
                "fields": {k: encode(v, assets, dropped, f"{at}.{k}")
                           for k, v in dataclasses.asdict(value).items()}}
    if isinstance(value, (list, tuple)):
        return [encode(v, assets, dropped, f"{at}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        if "_local_masks" in value:
            from .local_mask_state import check
            check(value["_local_masks"])
        if '_local_grade_layers' in value:
            _check_local_grade_record(value['_local_grade_layers'])
        if '_effect_recovery' in value:
            _check_effect_recovery_record(value['_effect_recovery'])
        if '_manual_liquify' in value:
            _check_manual_liquify_record(value['_manual_liquify'])
        if '_brow_shape' in value:
            from .brow_shape_project import validate_records
            validate_records(value)
        if '_eye_shape' in value:
            from .eye_shape_project import validate_records
            validate_records(value)
        if '_primary_calibration' in value:
            from .primary_calibration_native import admit as admit_primary
            admit_primary(value['_primary_calibration'])
        if '_colour_editor' in value:
            from .colour_editor_state import check as check_editor
            check_editor(value['_colour_editor'])
        if '_selective_colour' in value:
            from .selective_colour_state import check as check_selective
            check_selective(value['_selective_colour'])
        if '_colour_grading' in value:
            from .colour_grading_state import check as check_grading
            check_grading(value['_colour_grading'])
        if '_photo_grain' in value:
            from .photo_grain_state import check as check_grain
            check_grain(value['_photo_grain'])
        if '_photo_detail' in value:
            from .photo_detail_state import check as check_photo_detail
            check_photo_detail(value['_photo_detail'])
        if '_extended_tone' in value:
            from .extended_tone_state import check as check_extended_tone
            check_extended_tone(value['_extended_tone'])
        if '_reference_color' in value: validate_reference(value)
        if '_semantic_colour' in value: validate_semantic_colour(value)
        if '_body_pose_bank' in value: validate_body_pose(value)
        if '_mouth_shape' in value:
            from .mouth_shape_project import validate_records
            validate_records(value)
        if '_nose_shape' in value:
            from .nose_shape_project import validate_records
            validate_records(value)
        if '_lip_makeup' in value:
            from .lip_makeup_project import check_saved
            check_saved(value['_lip_makeup'])
        if '_optics' in value:
            from .optics_project import validate_records
            validate_records(value)
        if '_sky_replacement' in value:
            from .sky_replacement_state import check_saved_record
            check_saved_record(value['_sky_replacement'])
        if '_id_background' in value:
            from .id_background_project import validate_records as validate_id_background
            validate_id_background(value, assets=assets)
        if '_studio_background' in value:
            from .studio_background_state import check_saved_record
            check_saved_record(value['_studio_background'])
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                dropped.append({"at": at, "reason": f"字典键 {k!r} 不是字符串"})
                continue
            out[k] = encode(v, assets, dropped, f"{at}.{k}")
        return out
    # torch 张量与其它活对象：常驻产物，重挂得走引擎那条重放路，不塞进项目文件
    dropped.append({"at": at, "reason": f"类型 {type(value).__name__} 不可序列化，"
                                        "已丢弃（常驻张量随会话重建）"})
    return None


def _encode_array(arr: np.ndarray, assets: dict, dropped: list, at: str) -> object:
    """uint8 的掩膜/覆盖度走 PNG，其余走 raw。

    上限卡的是**写进文件的有载荷字节数**（base64 还要再 ×4/3），而不是数组原始字节：
    一张 4000×3000 的换底遮罩原始 12 MB，PNG 可能只几百 KB，拒掉它就是“保存成功
    而下次打开少了一半配方”；反过来一桌噪点表压不动，才真需要卡。这里的数字
    按本机实测形状写：3000×3000 均匀噪点的 PNG 约 9.0 MB（压不动），而同一尺寸的
    遮罩压到几百 KB。两个都在上限两侧，所以这条判据量得出方向。
    """
    mode = _png_mode(arr)
    if mode is not None:
        raw, kind = _png_bytes(arr), "png"
    else:
        raw, kind = arr.tobytes(), "raw"
    if len(raw) > MAX_ASSET_BYTES:
        dropped.append({"at": at, "reason": f"数组 {arr.shape} {arr.dtype} 编后 "
                                            f"{len(raw)} 字节（原始 {arr.nbytes}），"
                                            f"超过单资产上限 {MAX_ASSET_BYTES}"})
        return None
    return _encode_blob(raw, assets, dropped, at, kind=kind,
                        shape=list(arr.shape), dtype=str(arr.dtype))


def _encode_blob(raw: bytes, assets: dict, dropped: list, at: str, *, kind: str,
                 shape: list | None = None, dtype: str | None = None) -> object:
    digest = hashlib.sha256(raw).hexdigest()
    ref = f"sha256:{digest}"
    if ref not in assets:               # 内容寻址去重：二十张图共用一张表就只有一份
        assets[ref] = {"kind": kind, "shape": shape, "dtype": dtype,
                       "bytes": len(raw),
                       "b64": base64.b64encode(raw).decode("ascii")}
    return {"__asset__": ref, "at": at}


def decode(value: object, assets: dict, dropped: list, at: str,
           dc_types: dict | None = None) -> object:
    """`encode()` 的逆。dc_types 由调用方给（server 认得 RepairOp/LightOp），
    本层不 import 计算模块——持久层反向依赖 GPU 管线会形成循环，
    而且让"读一个 JSON"这件事取决于 torch 在不在。"""
    if isinstance(value, dict):
        if "__custom_cube__" in value:
            from .custom_lut_asset import CustomCube
            from .custom_lut_native import MAX_BYTES
            if set(value) != {"__custom_cube__", "asset", "sha256", "name"} or type(value["__custom_cube__"]) is not int or value["__custom_cube__"] != 1: raise ProjectError("自定义 LUT 标记无效")
            ref = value["asset"]
            key = "sha256:" + str(value["sha256"])
            if not isinstance(ref, dict) or ref.get("__asset__") != key: raise ProjectError("自定义 LUT 资产标识无效")
            asset = assets.get(key)
            if not isinstance(asset, dict) or asset.get("kind") != "custom-cube": raise ProjectError("自定义 LUT 资产缺失；未丢弃后继续打开")
            text = asset.get("b64")
            if not isinstance(text, str) or len(text) > ((MAX_BYTES+2)//3)*4: raise ProjectError("自定义 LUT 资产超过预算")
            try:
                raw = base64.b64decode(text, validate=True)
                if asset.get("bytes") != len(raw): raise ValueError("资产长度不一致")
                return CustomCube(raw, value["sha256"], value["name"])
            except Exception as error: raise ProjectError(f"自定义 LUT 重建失败，未静默丢弃：{error}") from error
        if '_local_grade_layers' in value:
            _check_local_grade_record(value['_local_grade_layers'])
        if '_effect_recovery' in value:
            _check_effect_recovery_record(value['_effect_recovery'])
        if '_manual_liquify' in value:
            _check_manual_liquify_record(value['_manual_liquify'])
        if '_brow_shape' in value:
            from .brow_shape_project import validate_records
            validate_records(value)
        if '_eye_shape' in value:
            from .eye_shape_project import validate_records
            validate_records(value)
        if '_primary_calibration' in value:
            from .primary_calibration_native import admit as admit_primary
            admit_primary(value['_primary_calibration'])
        if '_colour_editor' in value:
            from .colour_editor_state import check as check_editor
            check_editor(value['_colour_editor'])
        if '_selective_colour' in value:
            from .selective_colour_state import check as check_selective
            check_selective(value['_selective_colour'])
        if '_colour_grading' in value:
            from .colour_grading_state import check as check_grading
            check_grading(value['_colour_grading'])
        if '_photo_grain' in value:
            from .photo_grain_state import check as check_grain
            check_grain(value['_photo_grain'])
        if '_photo_detail' in value:
            from .photo_detail_state import check as check_photo_detail
            check_photo_detail(value['_photo_detail'])
        if '_extended_tone' in value:
            from .extended_tone_state import check as check_extended_tone
            check_extended_tone(value['_extended_tone'])
        if '_reference_color' in value: validate_reference(value)
        if '_semantic_colour' in value: validate_semantic_colour(value)
        if '_body_pose_bank' in value: validate_body_pose(value)
        if '_mouth_shape' in value:
            from .mouth_shape_project import validate_records
            validate_records(value)
        if '_nose_shape' in value:
            from .nose_shape_project import validate_records
            validate_records(value)
        if '_lip_makeup' in value:
            from .lip_makeup_project import check_saved
            check_saved(value['_lip_makeup'])
        if '_optics' in value:
            from .optics_project import validate_records
            validate_records(value)
        if '_sky_replacement' in value:
            from .sky_replacement_state import check_saved_record
            check_saved_record(value['_sky_replacement'])
        if '_id_background' in value:
            from .id_background_project import validate_records as validate_id_background
            validate_id_background(value, assets=assets)
        if '_studio_background' in value:
            from .studio_background_state import check_saved_record
            check_saved_record(value['_studio_background'])
        if value.get("__dc__") == "RepairOp":
            fields = _repair_fields(value, assets)
            cls = (dc_types or {}).get("RepairOp", RepairOp)
            try:
                return cls(**fields)
            except (TypeError, ValueError) as error:
                raise ProjectError(f"RepairOp reconstruction failed: {error}") from error
        if "__asset__" in value:
            a = assets.get(value["__asset__"])
            if a is None:
                dropped.append({"at": at, "reason": f"资产缺失 {value['__asset__']}"})
                return None
            raw = base64.b64decode(a["b64"])
            if hashlib.sha256(raw).hexdigest() != value["__asset__"].split(":", 1)[1]:
                dropped.append({"at": at, "reason": "资产内容与哈希对不上，已丢弃"})
                return None
            try:
                if a["kind"] == "png":
                    return _from_png_bytes(raw, a["shape"] or [])
                if a["kind"] == "raw":
                    return np.frombuffer(raw, dtype=np.dtype(a["dtype"])).reshape(a["shape"])
            except (ValueError, TypeError) as e:
                # 哈希对得上而形状拼不回去：那只可能是记录本身被改过。这里丢弃并记原因，
                # 不拿一个“看着像”的形状凑数——凑出来的配方比缺少的配方更难查
                dropped.append({"at": at, "reason": f"资产 {value['__asset__']} 重建失败：{e}"})
                return None
            return raw                      # bytes
        if "__dc__" in value:
            cls = (dc_types or {}).get(value["__dc__"])
            if cls is None and value["__dc__"] == "FacePrecompute":
                from .face import FacePrecompute
                cls = FacePrecompute
            if cls is None:
                dropped.append({"at": at, "reason": f"不认识的数据类 {value['__dc__']}"})
                return None
            fields = {k: decode(v, assets, dropped, f"{at}.{k}", dc_types)
                      for k, v in (value.get("fields") or {}).items()}
            try:
                return cls(**fields)
            except (TypeError, ValueError) as e:
                dropped.append({"at": at, "reason": f"{value['__dc__']} 重建失败：{e}"})
                return None
        if _REPAIR_STACKS.intersection(value):
            _validate_encoded_repairs(value, assets, allow_legacy=True)
        return {k: decode(v, assets, dropped, f"{at}.{k}", dc_types)
                for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v, assets, dropped, f"{at}[{i}]", dc_types)
                for i, v in enumerate(value)]
    return value


# ---------------------------------------------------------------- 文档行
def writer_stamp() -> dict:
    """写下这份工程当时的依赖形状（P0-*-NEUTRAL 那组里“依赖版本一致”就落在这一格）。

    为什么只记版本而不记更多：同一份配方在 numpy/torch 换版本后重算，舍入方向可能不
    同（16-bit 主链那一 LSB 的差就是在这上面出的）。重开时比一下就能把“画得不一样”
    归因到“写它的不是这个环境”，而不是让用户对着一个无从知道的差异猜。记的是包元数据
    （importlib.metadata），**不 import torch**：读一个 JSON 不该取决于 GPU 运行时在不在，
    而那个 import 要几秒。
    """
    from importlib import metadata
    from . import __version__ as engine_version
    out = {"engine": str(engine_version),
           "python": ".".join(map(str, sys.version_info[:3]))}
    for pkg in ("numpy", "pillow", "torch"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None       # 没装就写 None：与 runtime_report 同一规矩，不静默省略键
    return out


def new_project(name: str, root: str = "") -> dict:
    if not str(name).strip():
        raise ProjectError("项目名不能是空的：底片条与工程列表里它得有个能指认的名字")
    project = {"schema_version": SCHEMA, "project_id": str(uuid.uuid4()),
            "name": str(name).strip(), "root": os.path.abspath(root or os.getcwd()),
            "created_ns": int(time.time_ns()), "updated_ns": int(time.time_ns()),
            "engine": "LumaRetouch", "writer": writer_stamp(),
            "assets": {}, "source_assets": {}, "docs": [], "dropped": []}
    return VC.ensure_identity(project)


def project_path_for(directory: str, name: str, occupied=os.path.exists) -> str:
    """项目文件名：可读的名字 + 递编号后缀。同名的两个项目不能互相顶掉。

    只按名字命名会让第二次创建**覆盖**第一次的工程文件——那是“无提示覆盖”
    （EXPORT-001 同一个类别）发生在工程层，比丢一张导出更贵。这里默认按磁盘上
    在不在判，`occupied` 可注入是为了用例能连开两个同名的而不碰磁盘。
    不拿“名字 + 时间戳”当后缀：那会造出一堆名字看不出差别的文件，
    而用户要在工程列表里认出它们。
    """
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(name)).strip("._")
    safe = safe or "project"
    d = os.path.abspath(directory)
    os.makedirs(d, exist_ok=True)
    stem = f"{safe}{SUFFIX}"
    if not occupied(os.path.join(d, stem)):
        return os.path.join(d, stem)
    for i in range(2, 1000):
        cand = os.path.join(d, f"{safe}-{i}{SUFFIX}")
        if not occupied(cand):
            return cand
    raise ProjectError(f"同名项目文件太多（{safe} 一直排到 999）：换个项目名")


def find_doc(project: dict, path: str | None = None, *,
             document_id: str | None = None) -> dict | None:
    """Resolve explicit document identity, never silently choose a same-path row."""
    if document_id is not None:
        matches = [row for row in project["docs"] if row.get("document_id") == document_id]
        if len(matches) > 1:
            raise ProjectError(f"Duplicate document identity: {document_id}")
        row = matches[0] if matches else None
        if row is not None and path is not None and row["path"] != os.path.abspath(str(path)):
            raise ProjectError("document_id and path identify different source bindings")
        return row
    if path is None:
        raise ProjectError("A document_id or unambiguous path is required")
    want = os.path.abspath(str(path))
    matches = [row for row in project["docs"] if row["path"] == want]
    if len(matches) > 1:
        raise ProjectError(f"Ambiguous source path; select a document_id: {want}")
    return matches[0] if matches else None


def add_doc(project: dict, path: str, recipe: object, *, fp: dict | None = None,
            tags=None, dc_types: dict | None = None, budget: int | None = None,
            version_id: str | None = None, version_name: str = "live",
            document_id: str | None = None, source_asset_id: str | None = None,
            root_document_id: str | None = None, copy_number: int | None = None,
            recipe_version_id: str | None = None, trashed: bool | None = None) -> dict:
    """Save an explicitly owned document, retaining legacy unambiguous path calls.

    New linked rows need document_id/source_asset_id/root_document_id/copy_number.
    Merely supplying the same path never creates a copy or merges independent
    sources. Version IDs keep their existing named-version semantics; the row's
    separate recipe_version_id remains stable across edits and saves.
    """
    if recipe is not None:
        try:
            recipe = WB.normalize_state(recipe)
            if project.get("schema_version") in (MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA):
                _check_manual_liquify_record(recipe.get("_manual_liquify"))
            from .sky_replacement_project import validate_records as validate_sky
            validate_sky(recipe,required=(project.get("schema_version") in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),allowed=(project.get("schema_version") in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),semantic=(project.get("schema_version") in (SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
            from .brow_shape_project import validate_records as validate_brows
            from .nose_shape_project import validate_records as validate_noses
            from .eye_shape_project import validate_records as validate_eyes
            from .mouth_shape_project import validate_records as validate_mouth
            from .lip_makeup_project import validate_records as validate_lips
            validate_lips(recipe); validate_brows(recipe); validate_noses(recipe); validate_eyes(recipe); validate_mouth(recipe); validate_reference(recipe); validate_semantic_colour(recipe); validate_body_pose(recipe)
            from .optics_project import validate_records as validate_optics
            validate_optics(recipe,required=(project.get("schema_version") in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)),allowed=(project.get("schema_version") in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
            from .studio_background_project import validate_records as validate_studio
            validate_studio(recipe, required=(project.get("schema_version") in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)), allowed=(project.get("schema_version") in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
            for key in _REPAIR_STACKS.intersection(recipe):
                validate_repair_ops(recipe[key], shape=recipe.get("_proxy"))
        except ValueError as error:
            raise ProjectError(f"Invalid project recipe: {error}") from error
    fp = copy.deepcopy(fp) if fp is not None else fingerprint(path, full=True)
    want = os.path.abspath(str(path))
    if fp.get("path", want) != want:
        raise ProjectError("Source fingerprint path does not match the requested document")
    fp["path"] = want
    dropped: list = []
    assets = dict(project.get("assets", {}))
    enc = encode(recipe, assets, dropped, "recipe") if recipe is not None else None
    _validate_encoded_repairs(enc, assets, allow_legacy=False,
                              require_manual_liquify=(project.get("schema_version") in (MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)))
    original = find_doc(project, want, document_id=document_id)
    row = copy.deepcopy(original) if original is not None else None
    if row is None:
        did = document_id or str(uuid.uuid4())
        row = {"path": want, "fingerprint": fp, "tags": list(tags or []),
               "label": None, "trashed": bool(trashed), "added_ns": int(time.time_ns()),
               "versions": [], "active_version": None, "budget": budget,
               "document_id": did, "source_asset_id": source_asset_id or str(uuid.uuid4()),
               "root_document_id": root_document_id or did,
               "copy_number": 0 if copy_number is None else copy_number,
               "recipe_version_id": recipe_version_id or str(uuid.uuid4())}
        if trashed is None and row["root_document_id"] != did:
            root = find_doc(project, document_id=row["root_document_id"])
            row["trashed"] = bool(root and root.get("trashed", False))
    else:
        if row.get("document_id") is None:
            VC.ensure_identity({"project_id": project["project_id"], "docs": [row]})
        for key, requested in (("document_id", document_id), ("source_asset_id", source_asset_id),
                               ("root_document_id", root_document_id), ("copy_number", copy_number),
                               ("recipe_version_id", recipe_version_id)):
            if requested is not None and row.get(key) != requested:
                raise ProjectError(f"Immutable document identity cannot change: {key}")
    # Stage identity changes before touching the live project, including sibling
    # fingerprint updates. A failed binding must not leave a half-added copy.
    if trashed is not None:
        row["trashed"] = bool(trashed)
    staged_rows = [(current, row if current is original else copy.copy(current))
                   for current in project["docs"]]
    candidate = {**project, "source_assets": copy.deepcopy(project.get("source_assets", {})),
                 "docs": [staged for _, staged in staged_rows] + ([] if original is not None else [row])}
    try:
        VC.ensure_identity(candidate)
        source = VC.register_source(candidate, row["source_asset_id"], want, fp)
        VC.validate_identity(candidate)
    except (ValueError, TypeError, KeyError) as error:
        raise ProjectError(f"Invalid document/source identity: {error}") from error
    if tags is not None:
        row["tags"] = list(tags)
    vid = version_id or str(uuid.uuid4())
    ver = next((v for v in row["versions"] if v["id"] == vid), None)
    if ver is None:
        ver = {"id": vid}
        row["versions"].append(ver)
    ver.update({"name": version_name, "created_ns": int(time.time_ns()), "recipe": enc,
                # 代理档跟着配方走：那一档上的逐点层（逐点掩膜/笔迹/形变场）尺寸不对就是
                # 无效配方。不记这一笔，重开时只能拿“图在不在”猜，而猜错的表现是渲染半截画面
                "proxy": (recipe.get("_proxy") if isinstance(recipe, dict) else None)})
    row["active_version"] = vid
    row["fingerprint"] = copy.deepcopy(source["fingerprint"])
    project["assets"] = assets
    project["source_assets"] = candidate["source_assets"]
    for current, staged in staged_rows:
        current.update(staged)
    if original is None:
        project["docs"].append(row)
    else:
        original.update(row)
        row = original
    if dropped:
        project.setdefault("dropped", []).extend(
            [{"path": fp["path"], **d} for d in dropped])
    return row


def active_recipe(project: dict, path: str | None = None, dc_types: dict | None = None, *,
                  document_id: str | None = None) -> object:
    row = find_doc(project, path, document_id=document_id)
    if row is None:
        raise ProjectError(f"项目里没有这一张：{path}")
    vid = row.get("active_version")
    for v in row.get("versions", []):
        if v["id"] == vid:
            recipe = v.get("recipe")
            if project.get("schema_version") in (MANUAL_SCHEMA, STUDIO_SCHEMA, OPTICS_SCHEMA, SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA) and recipe is not None:
                if type(recipe) is not dict:
                    raise ProjectError("Project v7 recipe must be an object")
                _check_manual_liquify_record(recipe.get("_manual_liquify"))
                from .sky_replacement_project import validate_records as validate_sky
                validate_sky(recipe,required=(project.get("schema_version") in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),allowed=(project.get("schema_version") in (SKY_SCHEMA, SEMANTIC_SKY_SCHEMA, SEMANTIC_COLOUR_SCHEMA, BODY_SCHEMA, HAIR_SCHEMA, CUBE_SCHEMA, TONE_SCHEMA, GRADING_SCHEMA, SELECTIVE_SCHEMA, PRIMARY_SCHEMA, DETAIL_SCHEMA, GRAIN_SCHEMA, COLOUR_EDITOR_SCHEMA, SCHEMA)),semantic=(project.get("schema_version") in (SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
                from .brow_shape_project import validate_records as validate_brows
                from .nose_shape_project import validate_records as validate_noses
                from .eye_shape_project import validate_records as validate_eyes
                from .mouth_shape_project import validate_records as validate_mouth
                from .lip_makeup_project import validate_records as validate_lips
                validate_lips(recipe); validate_brows(recipe); validate_noses(recipe); validate_eyes(recipe); validate_mouth(recipe); validate_reference(recipe); validate_semantic_colour(recipe); validate_body_pose(recipe)
                from .optics_project import validate_records as validate_optics
                validate_optics(recipe,required=(project.get("schema_version") in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)),allowed=(project.get("schema_version") in (OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
                from .studio_background_project import validate_records as validate_studio
                validate_studio(recipe, required=(project.get("schema_version") in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)), allowed=(project.get("schema_version") in (STUDIO_SCHEMA,OPTICS_SCHEMA,SKY_SCHEMA,SEMANTIC_SKY_SCHEMA,SEMANTIC_COLOUR_SCHEMA,BODY_SCHEMA,HAIR_SCHEMA,CUBE_SCHEMA,TONE_SCHEMA,GRADING_SCHEMA,SELECTIVE_SCHEMA,PRIMARY_SCHEMA,DETAIL_SCHEMA,GRAIN_SCHEMA,COLOUR_EDITOR_SCHEMA,SCHEMA)))
                _validate_encoded_repairs(recipe, project.get("assets") or {}, allow_legacy=False,
                                          require_manual_liquify=True)
            dropped: list = []
            return decode(recipe, project.get("assets") or {}, dropped,
                          "recipe", dc_types), dropped
    raise ProjectError(f"{path} 的活动版本 {vid!r} 在 versions 里找不到（半个配方）")


def put_active_version(project: dict, path: str | None, version_id: str, *,
                       document_id: str | None = None) -> dict:
    """切"活动版本"。找不到就拒——静默切到不存在的版本，下次打开显示的就是别人的配方。"""
    row = find_doc(project, path, document_id=document_id)
    if row is None:
        raise ProjectError(f"项目里没有这一张：{path}")
    if not any(v["id"] == version_id for v in row.get("versions", [])):
        raise ProjectError(f"{row['path']} 没有版本 {version_id!r}（可用："
                           f"{[v['id'] for v in row.get('versions', [])]}）")
    row["active_version"] = version_id
    return row


def set_trashed(project: dict, path: str | None, on: bool, *,
                document_id: str | None = None) -> dict:
    """Soft-delete/restore project records only; original source bytes are untouched."""
    row = find_doc(project, path, document_id=document_id)
    if row is None:
        raise ProjectError(f"项目里没有这一张：{document_id or path}")
    if row.get("document_id") is None:
        row["trashed"] = bool(on)
    else:
        try:
            VC.set_trashed(project, row["document_id"], on)
        except (ValueError, TypeError, KeyError) as error:
            raise ProjectError(str(error)) from error
    return row


def set_tags(project: dict, path: str | None, tags, *,
             document_id: str | None = None) -> dict:
    row = find_doc(project, path, document_id=document_id)
    if row is None:
        raise ProjectError(f"项目里没有这一张：{path}")
    out, bad = [], []
    for t in tags or []:
        if not isinstance(t, str) or not t.strip():
            bad.append(t)
            continue
        s = t.strip()
        if len(s) > 64:
            bad.append(f"{s[:16]}…（超过 64 字）")
            continue
        if s not in out:
            out.append(s)
    if bad:
        raise ProjectError(f"标签非法，整条拒绝：{bad}（要 1–64 字的非空字符串）")
    row["tags"] = out
    return row


def missing_sources(project: dict) -> list:
    """Report every document against its authoritative source, without path collapse."""
    out = []
    for row in project["docs"]:
        source = project.get("source_assets", {}).get(row.get("source_asset_id"), row)
        path, fp = source["path"], source.get("fingerprint") or {}
        exists = os.path.isfile(path)
        out.append({"path": path, "document_id": row.get("document_id"),
                    "source_asset_id": row.get("source_asset_id"), "exists": exists,
                    "bytes_match": bool(exists and os.path.getsize(path) == fp.get("bytes"))})
    return out
