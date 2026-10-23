"""项目持久化的单元用例（LNX-P0-PROJECT；验收 CORE-001 / CORE-007 / CORE-008）。

这一层的判据只围绕一句话：**"保存成功"与"打开后少了一半配方"不能长得一样**。
所以每条都在读回来的文件/结构上反查，不在内存里自证；凡"丢弃"都必须留下原因。

不 import torch / vram：持久层反向依赖计算模块会形成循环，而且这条路在没装
计算层的机器上也必须是能测的（CI 的开发 venv 就是那台机器）。
"""
from __future__ import annotations

import dataclasses
import json
import os

import numpy as np
import pytest

from lumaretouch_engine import project as P, manual_liquify_state as ML


@dataclasses.dataclass
class Op:
    """长得像 RepairOp/LightOp 的替身：一个整型 id、一个 uint8 覆盖度、一个浮点增益。"""
    op_id: int
    cover: np.ndarray
    gain: float


@pytest.fixture
def src(tmp_path):
    from PIL import Image
    p = tmp_path / "a.png"
    a = np.zeros((32, 24, 3), np.uint8)
    a[..., 1] = np.arange(32)[:, None]
    Image.fromarray(a, "RGB").save(p)
    return str(p)


def _recipe():
    return {"_manual_liquify": ML.empty(), "_strength": 0.4, "_params": {"radius": 12, "eps": 0.02},
            "_grade": (0.1, -0.2, 0.0, 0.8), "_exposure": (0.5, -100.0, 0.0),
            "_crop_rect": (0.1, 0.2, 0.7, 0.95), "_crop_rotation": -7.5,
            "_lut": None, "_lut_amount": 1.0, "_channel": "skin",
            "_fixture_ops": [Op(1, np.arange(8 * 8, dtype=np.uint8).reshape(8, 8), 0.25)],
            "_light_ops": [], "_precompute": None, "_proxy": (32, 24)}


# ---------------------------------------------------------------- 往返
def test_round_trip_restores_docs_tags_trash_and_recipe(tmp_path, src):
    """CORE-001 的 then：照片集合、标签、活动版本和配方完整恢复。"""
    prj = P.new_project("婚礼试装", str(tmp_path))
    P.add_doc(prj, src, _recipe(), tags=["已交", "待确认"])
    P.set_trashed(prj, src, True)
    path = P.project_path_for(str(tmp_path), "婚礼试装")
    facts = P.save(prj, path)
    assert facts["bytes"] == os.path.getsize(path) > 0

    back = P.load(path)
    assert back["project_id"] == prj["project_id"], "重开换了 id，工程列表就认不出这是同一个项目"
    assert back["name"] == "婚礼试装"
    row = P.find_doc(back, src)
    assert row is not None and row["trashed"] is True
    assert row["tags"] == ["已交", "待确认"]
    recipe, dropped = P.active_recipe(back, src, dc_types={"Op": Op})
    assert dropped == [], f"往返路上丢了东西：{dropped}"
    assert recipe["_strength"] == 0.4 and recipe["_crop_rotation"] == -7.5
    assert recipe["_grade"] == [0.1, -0.2, 0.0, 0.8]
    op = recipe["_fixture_ops"][0]
    assert isinstance(op, Op) and op.op_id == 1 and float(op.gain) == 0.25
    assert np.array_equal(op.cover, np.arange(64, dtype=np.uint8).reshape(8, 8))


def test_source_hash_is_unchanged_by_the_project(tmp_path, src):
    """CORE-001 的最后一句"源文件哈希不变"：本项目对原图只读。

    指纹本身也得是被验过的读法：`open(path, "rb")` 不写、不改 mtime。
    哈希算完发现文件动过，最可能的解释就是自己动的手。
    """
    before = (open(src, "rb").read(), os.stat(src).st_mtime_ns)
    prj = P.new_project("p", str(tmp_path))
    fp = P.add_doc(prj, src, _recipe())["fingerprint"]
    after = (open(src, "rb").read(), os.stat(src).st_mtime_ns)
    assert before[0] == after[0] and before[1] == after[1], "打指纹这一步碰了源文件"
    import hashlib
    # v23 source identities require complete byte evidence when adding a document.
    # UNRUN: virtual-copy migration changes the previous head-only default.
    assert fp["hash_level"] == "full" and fp["sha256"] == hashlib.sha256(after[0]).hexdigest(), fp
    full = P.fingerprint(src, full=True)
    assert full["hash_level"] == "full"
    assert full["sha256"] == hashlib.sha256(after[0]).hexdigest()


def test_fingerprint_bytes_is_the_real_size_over_chunk_boundary(tmp_path):
    """长度必须是字节数，不是“读了几个块”。

    第一版的 head 快路径把剩下的 1 MB 块数直接加进 n，跨 1 MB 边界的文件会少报
    几 MB；而 verify 拿这个数判“图被动过没动过”，错的方向是“变了说成没变”。
    """
    big = tmp_path / "big.bin"
    data = np.random.default_rng(1).integers(0, 256, size=(2_500_000,), dtype=np.uint8)
    big.write_bytes(data.tobytes())
    for full in (False, True):
        fp = P.fingerprint(str(big), full=full)
        assert fp["bytes"] == data.nbytes == os.path.getsize(str(big)), (full, fp["bytes"])


def test_verify_fingerprint_separates_missing_from_touched(tmp_path, src):
    # 验收用例引用：CORE-005（缺失与被改分开报：哈希不同就必须说"源变了"并失效旧缓存）
    """重开时的三种“不对”处置不同，必须分开报（与 missing_sources 同一理由）。

    缺文件是“在哪”；只改 mtime 是拷贝/同步工具干的，不该报成“照片坏了”；
    head 对不上才是真被动过。
    """
    gone = str(tmp_path / "nope.jpg")
    fp = P.fingerprint(src)
    assert P.verify_fingerprint(src, fp)["head_match"] is True
    assert P.verify_fingerprint(gone, fp)["exists"] is False
    os.utime(src, ns=(1_000_000_000, 1_000_000_000))
    v = P.verify_fingerprint(src, fp)
    assert v["head_match"] and v["bytes_match"] and v["mtime_moved_only"] is True, v
    with open(src, "ab") as f:
        f.write(b"x")
    v2 = P.verify_fingerprint(src, fp)
    assert v2["head_match"] is False and v2["bytes_match"] is False, v2


def test_same_path_never_gets_two_rows(tmp_path, src):
    """同一路径不许出现第二行：validate() 会拒重复 path，所以这条是换行而不是加行。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    P.add_doc(prj, src, _recipe())
    assert len(prj["docs"]) == 1
    P.validate(prj)                       # 换行之后仍然过得了结构校验


def test_named_version_id_is_overwritten_not_appended(tmp_path, src):
    """“当前配方”在工程文件里只能有一格，而它的身份要在多次保存之间稳定。

    不传 id 时每次保存都新造一版：那会把工程文件写成历史堆（每版一套资产），
    而重开后宿主拿到的 active_version 与上次看到的不是同一个名字。
    """
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe(), version_id="live")
    r2 = _recipe()
    r2["_strength"] = 0.9
    P.add_doc(prj, src, r2, version_id="live")
    row = prj["docs"][0]
    assert len(row["versions"]) == 1 and row["active_version"] == "live", row
    got, _ = P.active_recipe(prj, src, dc_types={"Op": Op})
    assert got["_strength"] == 0.9, "按 id 覆盖没生效，拿到的还是旧配方"
    # 命名版本（不传 id）仍然逐格累加：那是用户主动存的，不是“当前”
    P.add_doc(prj, src, r2, version_name="交稿前")
    assert len(prj["docs"][0]["versions"]) == 2


def test_recycle_bin_does_not_touch_the_file(tmp_path, src):
    """CORE-007：移入回收站再恢复——原图不删除，配方仍在。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    P.set_trashed(prj, src, True)
    assert os.path.isfile(src)
    recipe, dropped = P.active_recipe(prj, src, dc_types={"Op": Op})
    assert recipe is not None and dropped == []
    P.set_trashed(prj, src, False)
    assert P.find_doc(prj, src)["trashed"] is False


# ---------------------------------------------------------------- 原子性与损坏
def test_failed_save_leaves_the_old_file_and_no_temp(tmp_path, src, monkeypatch):
    """CORE-008 的注入版：写一半失败，磁盘上只能是**完整旧版本**。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    path = P.project_path_for(str(tmp_path), "p")
    P.save(prj, path)
    old = open(path, "rb").read()

    def boom(*_a, **_k):
        raise OSError("注入：替换这一步失败")
    monkeypatch.setattr(os, "replace", boom)
    prj2 = P.load(path)
    with pytest.raises(OSError):
        P.save(prj2, path)
    assert open(path, "rb").read() == old, "旧版本被动过了"
    leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    assert leftovers == [], f"临时文件留在工程目录里：{leftovers}"


def test_nan_in_recipe_is_refused_not_written(tmp_path, src):
    """NaN 不能进 JSON：默认 dumps 会写出 `NaN` 这种非法字面量，下次加载才炸。

    那就是"半个配方"的形状——当场能编、文件也在、打开才坏。
    """
    prj = P.new_project("p", str(tmp_path))
    r = _recipe()
    r["_grade"] = (float("nan"), 0.0, 0.0, 1.0)
    P.add_doc(prj, src, r)
    assert prj["dropped"], "NaN 应当被 encode 记进 dropped"
    path = P.project_path_for(str(tmp_path), "p")
    info, _ = P.active_recipe(prj, src, dc_types={"Op": Op})
    assert info["_grade"][0] is None          # encode 把 NaN 记下来并置 None
    P.save(prj, path)                          # 到这一步不该因为 NaN 写出非法 JSON
    back = P.load(path)
    assert P.active_recipe(back, src, dc_types={"Op": Op})[1] == []


def test_truncated_file_is_reported_as_damage_not_missing(tmp_path, src):
    """半截文件要报成"损坏"，不是笼统一句"打不开"：那是两种处置。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    path = P.project_path_for(str(tmp_path), "p")
    P.save(prj, path)
    raw = open(path, "rb").read()
    with open(path, "wb") as f:
        f.write(raw[: len(raw) // 2])
    with pytest.raises(P.ProjectError) as e:
        P.load(path)
    assert "损坏" in str(e.value), str(e.value)


@pytest.mark.parametrize("mutate", ["dup_path", "missing_key", "bad_schema", "docs_shape",
                                    "no_active_version", "versions_shape"])
def test_validate_rejects_bad_shapes(tmp_path, src, mutate):
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    if mutate == "dup_path":
        prj["docs"].append(dict(prj["docs"][0]))
    elif mutate == "missing_key":
        del prj["assets"]
    elif mutate == "bad_schema":
        prj["schema_version"] = "lrt.project.v0"
    elif mutate == "no_active_version":
        del prj["docs"][0]["active_version"]
    elif mutate == "versions_shape":
        prj["docs"][0]["versions"] = {"not": "a list"}
    else:
        prj["docs"] = {"not": "a list"}
    with pytest.raises(P.ProjectError):
        P.validate(prj)


# ---------------------------------------------------------------- 编解码
def test_uint8_mask_survives_byte_identical(tmp_path):
    """画笔覆盖度是证据，不是缩略图：PNG 那条路必须逐字节回来。"""
    a = (np.arange(64 * 40, dtype=np.uint8).reshape(64, 40) * 7)[:, :, None]
    assets, dropped = {}, []
    ref = P.encode(a, assets, dropped, "recipe.x")
    assert dropped == [] and ref["__asset__"].startswith("sha256:")
    assert assets[ref["__asset__"]]["kind"] == "png"
    got = P.decode(ref, assets, dropped, "recipe.x")
    assert dropped == []
    assert np.array_equal(np.asarray(got), a)


def test_float_lut_table_survives_byte_identical():
    """调色表原件是 float：它走 raw 资产，绝不能被降成 8-bit"差不多"。"""
    t = (np.random.default_rng(7).random((8, 8, 3)) * 255).astype(np.float32)
    assets, dropped = {}, []
    ref = P.encode(t, assets, dropped, "recipe.lut")
    assert assets[ref["__asset__"]]["kind"] == "raw"
    got = P.decode(ref, assets, [], "recipe.lut")
    assert np.array_equal(np.asarray(got, np.float32), t)


def test_identical_assets_are_stored_once():
    """内容寻址去重：二十张图共用一张表，文件里就该只有一份。

    不去重的后果不是"文件大一点"：项目文件整份进内存再解析，几十张自定义调色表
    乘以二十张图就是打开工程时那几十秒。
    """
    t = np.zeros((33, 33, 33), np.float32)
    assets, dropped = {}, []
    for i in range(20):
        P.encode(t, assets, dropped, f"recipe.d{i}.lut")
    assert len(assets) == 1, f"同一张表被写了 {len(assets)} 份"


def test_oversize_array_is_recorded_not_written():
    """卡的是**编后写进文件的字节**，不是数组原始字节：方向要量对。

    3000×3000 均匀噪点压不动（≈ 9 MB），必须拒；同一尺寸的遮罩原始更大而 PNG
    只几百 KB，必须收——拿 nbytes 当判据就会把后者误杀，那就是一条“保存成功
    而打开后少了一半配方”的路。本仓的遮罩在真机档上就是后者。8 MB 上限的
    两侧各放一个形状，这条判据就不是拍脑袋。
    """
    noise = np.random.default_rng(3).integers(0, 256, size=(3000, 3000), dtype=np.uint8)
    assets, dropped = {}, []
    out = P.encode(noise, assets, dropped, "recipe.matte")
    assert out is None and len(assets) == 0
    assert dropped and "超过单资产上限" in dropped[0]["reason"], dropped
    assert dropped[0]["at"] == "recipe.matte", "得说清是哪一格没存进去"
    # 同一上限的另一侧：可压缩的大遮罩必须存得下
    matte = np.zeros((4000, 3000), np.uint8)
    matte[:1000] = 255
    assets2, dropped2 = {}, []
    ok = P.encode(matte, assets2, dropped2, "recipe.matte")
    assert ok is not None and dropped2 == [], (dropped2, assets2)


def test_unknown_object_leaves_a_reason():
    class Live:                        # 长得像 torch.Tensor 的那种活对象
        pass
    assets, dropped = {}, []
    out = P.encode({"_bg": {"matte": Live()}}, assets, dropped, "recipe")
    assert out["_bg"]["matte"] is None
    assert dropped and "不可序列化" in dropped[0]["reason"]
    assert dropped[0]["at"] == "recipe._bg.matte"


def test_dataclass_round_trip_and_unknown_class_records_reason():
    op = Op(3, np.full((4, 4), 200, np.uint8), 0.5)
    assets, dropped = {}, []
    enc = P.encode(op, assets, dropped, "recipe.ops[0]")
    assert enc["__dc__"] == "Op"
    back = P.decode(enc, assets, dropped, "recipe.ops[0]", dc_types={"Op": Op})
    assert isinstance(back, Op) and np.array_equal(back.cover, op.cover)
    lost = P.decode(enc, assets, [], "recipe.ops[0]", dc_types={})
    assert lost is None, "认不出的数据类不能假装重建成功"


def test_asset_hash_mismatch_is_dropped(tmp_path, src):
    """文件被人手改过一位：宁缺这一层，也不要"看起来恢复了"的半个配方。"""
    import base64
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    ref = next(iter(prj["assets"]))
    prj["assets"][ref]["b64"] = base64.b64encode(b"tampered").decode("ascii")
    _, dropped = P.active_recipe(prj, src, dc_types={"Op": Op})
    assert dropped and "对不上" in dropped[0]["reason"], dropped


def test_asset_shape_record_mismatch_is_dropped(tmp_path, src):
    """哈希对得上而记录形状被改：不能拿一个“看着像”的形状凑数。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    ref = next(iter(prj["assets"]))
    prj["assets"][ref]["shape"] = [7, 7, 1]      # 与原字节乘不上的形状
    _, dropped = P.active_recipe(prj, src, dc_types={"Op": Op})
    assert dropped and "重建失败" in dropped[0]["reason"], dropped


def test_missing_active_version_is_an_error(tmp_path, src):
    """活动版本指向一个不存在的版本 = 半个配方，必须响，不能退回"没调过"。"""
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    prj["docs"][0]["active_version"] = "no-such-version"
    with pytest.raises(P.ProjectError):
        P.active_recipe(prj, src, dc_types={"Op": Op})


# ---------------------------------------------------------------- 命名与清单
def test_two_projects_with_the_same_name_do_not_collide(tmp_path):
    """第二次创建不许覆盖第一次的工程：那是"无提示覆盖"发生在工程层。"""
    p1 = P.project_path_for(str(tmp_path), "婚礼")
    open(p1, "w").write("{}")
    p2 = P.project_path_for(str(tmp_path), "婚礼")
    assert p1 != p2 and p2.endswith("-2" + P.SUFFIX), (p1, p2)
    assert not os.path.exists(p2)


def test_project_path_survives_odd_names(tmp_path):
    p = P.project_path_for(str(tmp_path), "婚礼/2026:春 *?")
    assert os.path.dirname(p) == str(tmp_path.resolve())
    assert os.path.basename(p).endswith(P.SUFFIX)


def test_missing_sources_reports_per_row(tmp_path, src):
    # 验收用例引用：CORE-005（逐格显示缺失（不是整批一句"打不开"））
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe())
    gone = str(tmp_path / "missing.jpg")
    prj["docs"].append({"path": gone, "active": {},
                        "fingerprint": {"bytes": 123}, "tags": [], "versions": [],
                        "active_version": None, "trashed": False})
    rows = {r["path"]: r for r in P.missing_sources(prj)}
    assert rows[src]["exists"] is True and rows[src]["bytes_match"] is True
    assert rows[gone]["exists"] is False, "缺图必须逐条报出来，不能静默少一张"


def test_tags_are_validated_as_a_whole(tmp_path, src):
    prj = P.new_project("p", str(tmp_path))
    P.add_doc(prj, src, _recipe(), tags=["a"])
    with pytest.raises(P.ProjectError):
        P.set_tags(prj, src, ["好", "   ", 12])
    assert P.find_doc(prj, src)["tags"] == ["a"], "被拒的标签命令改写了已有标签"
    P.set_tags(prj, src, [" 重做 ", "重做", "b"])
    assert P.find_doc(prj, src)["tags"] == ["重做", "b"], "要去空白并去重"


def test_saved_file_is_plain_json_a_human_can_read(tmp_path, src):
    """"人能直接读那个文件"是选 JSON 的理由之一，那就把它当成一条断言。

    断言的是结构可读（非 ASCII 不转义、有缩进、顶层是对象），不是某个字段顺序。
    """
    prj = P.new_project("婚礼 春", str(tmp_path))
    P.add_doc(prj, src, _recipe(), tags=["已交"])
    path = P.project_path_for(str(tmp_path), "婚礼 春")
    P.save(prj, path)
    text = open(path, encoding="utf-8").read()
    assert "婚礼 春" in text, "非 ASCII 被转义成了 \\uXXXX，人读不动"
    assert "\n   \"" in text, "没有缩进，diff 起来整份文件都是改动"
    assert json.loads(text)["docs"][0]["tags"] == ["已交"]
