"""导出侧 P0 口径：ICC 嵌入、GPS 默认不外泄、冲突不覆盖、原子提交。

对应《开发验收用例》COLOR-001 / COLOR-002 / COLOR-003 / EXPORT-001。

这一组用例的共同要求是**读回文件反查**，而不是读引擎自己报的字段：一个声称
"icc_bytes=588"却把档写坏的实现，只有再打开一次文件才能发现。回报字段本身也验，
但它与文件内容不一致时必须是测试红。
"""
from __future__ import annotations

import os
import time

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine.export import (ExportError, _profile_bytes, resolve_target,
                                        write_file)


def _rgb(h=24, w=32):
    a = np.zeros((h, w, 3), np.uint8)
    a[..., 0] = np.linspace(10, 240, h)[:, None]
    a[..., 1] = 90
    a[..., 2] = np.linspace(200, 30, w)[None, :]
    return a


def _gps_exif(orient: int = 0):
    ex = Image.Exif()
    ex[0x010e] = "contact@example.invalid"          # ImageDescription，用来验证别的字段仍在
    if orient:
        ex[0x0112] = orient                          # Orientation：摆过的像素不能再带方向标
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = "2026:10:18 09:00:01"             # DateTimeOriginal（Exif 子 IFD）
    gps = ex.get_ifd(0x8825)
    gps[1] = "N"
    # RATIONAL 要的是数值（float/Fraction）而不是 (num, den) 元组：写成元组时
    # Pillow 在 tobytes() 里报 `bad operand type for abs(): 'tuple'`——而这一支
    # 只有 include_gps=True 才会序列化到，上一轮那条“默认不写 GPS”的用例
    # 把同一个夹具走了另一条路，所以它绿着、这个红——夹具本身不能只靠一条用例验
    gps[2] = (39.9, 54.5, 0.25)                     # 假的、可辨识的坐标
    return ex


# ------------------------------------------------------------------ ICC（COLOR-001/002）
def test_srgb_profile_is_embedded_and_readable_back(tmp_path):
    p = str(tmp_path / "a.jpg")
    info = write_file(_rgb(), p, quality=92)
    assert info["icc_bytes"] > 0 and info["icc_source"] == "srgb"
    got = Image.open(p)
    blob = got.info.get("icc_profile")
    assert blob, "回报说嵌了 ICC，文件里却没有——这就是只信自报值的下场"
    assert len(blob) == info["icc_bytes"], \
        f"报的 {info['icc_bytes']} B 与文件里的 {len(blob)} B 不一致"


def test_adobe_rgb_without_a_file_is_rejected_not_faked(tmp_path):
    """没有真档时必须拒，而不是烘一个"名字对内容错"的 profile。

    嵌错 ICC 比不嵌更坏：读方会拿错的那份去转色，颜色真的变了而文件里写着另一个名字。
    """
    with pytest.raises(ExportError, match="output_profile"):
        write_file(_rgb(), str(tmp_path / "b.jpg"), output_profile="adobergb")
    # 给了真实文件就通得过（机制本身不是障碍，缺资产才是）
    real = tmp_path / "prof.icc"
    real.write_bytes(_profile_bytes("srgb"))
    info = write_file(_rgb(), str(tmp_path / "c.jpg"), output_profile=str(real))
    assert info["icc_bytes"] == len(real.read_bytes())


def test_source_profile_without_source_is_rejected(tmp_path):
    with pytest.raises(ExportError, match="没有 ICC"):
        write_file(_rgb(), str(tmp_path / "d.jpg"), output_profile="source", source_icc=None)


# ------------------------------------------------------------------ GPS（COLOR-003）
def test_gps_is_absent_by_default_even_when_source_has_it(tmp_path):
    p = str(tmp_path / "e.jpg")
    info = write_file(_rgb(), p, source_exif=_gps_exif())
    assert info["gps_written"] is False
    out = Image.open(p)
    ex = out.getexif()
    assert not ex.get_ifd(0x8825), "默认路径把 GPS 写出去了——隐私用例直接失败"
    assert ex[0x010E] == "contact@example.invalid", "删 GPS 时把别的字段一起弄丢了"


def test_gps_present_only_when_explicitly_asked(tmp_path):
    p = str(tmp_path / "f.jpg")
    info = write_file(_rgb(), p, source_exif=_gps_exif(), metadata_include_gps=True)
    assert info["gps_written"] is True
    ex = Image.open(p).getexif()
    gps = ex.get_ifd(0x8825)
    assert gps and gps[1] == "N", f"开关开了却没写出 GPS：{dict(gps) if gps else '(空)'}"
    assert abs(float(gps[2][0]) - 39.9) < 1e-6, f"坐标写过去了但值不对：{gps[2]}"


def test_no_source_exif_means_no_exif_not_a_crash(tmp_path):
    info = write_file(_rgb(), str(tmp_path / "g.png"))
    assert info["exif_bytes"] == 0 and info["gps_written"] is False


# ------------------------------------------------------------------ 冲突（EXPORT-001）
def test_existing_file_is_never_overwritten_silently(tmp_path):
    p = tmp_path / "h.jpg"
    p.write_bytes(b"NOT-an-image-but-a-user's-work")
    before = p.read_bytes()
    info = write_file(_rgb(), str(p), conflict_policy="skip_and_report")
    assert info["skipped"] is True and info["bytes"] == 0
    assert p.read_bytes() == before, "skip 却动了已有文件"
    assert "已存在" in info["reason"]


def test_recheck_writes_a_unique_name_and_keeps_the_original(tmp_path):
    p = tmp_path / "i.jpg"
    p.write_bytes(b"original")
    info = write_file(_rgb(), str(p), conflict_policy="recheck")
    assert info["skipped"] is False
    assert info["path"] != str(p) and info["renamed_from"] == str(p)
    assert p.read_bytes() == b"original", "recheck 把原件改了"
    assert Image.open(info["path"]).size == (32, 24), "改名的产物不可解码或尺寸不对"


def test_overwrite_policy_is_rejected_as_a_category_error(tmp_path):
    """不是"未知策略宽容处理"：写覆盖会被静默当成 skip 或 recheck，那是更坏的行为。"""
    with pytest.raises(ExportError, match="没有 overwrite"):
        resolve_target(str(tmp_path / "x.jpg"), "overwrite")


# ------------------------------------------------------------------ 原子性
def test_no_temp_file_survives_a_successful_write(tmp_path):
    write_file(_rgb(), str(tmp_path / "j.png"))
    assert [f.name for f in tmp_path.iterdir()] == ["j.png"], "目录里留了临时文件"


def test_failure_during_commit_leaves_nothing_behind(tmp_path, monkeypatch):
    """编码后、改名前失败：目录必须干净，既不出现半成品也不损坏原件。"""
    p = tmp_path / "k.png"
    real = os.replace
    monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk gone")))
    with pytest.raises(OSError):
        write_file(_rgb(), str(p))
    monkeypatch.setattr("os.replace", real)
    assert list(tmp_path.iterdir()) == [], f"失败后留下现场：{[f.name for f in tmp_path.iterdir()]}"


def test_valid_combinations_still_work_after_the_plumbing(tmp_path):
    """回归护栏：改成“内存编码 + 原子提交”之后，各格式的可选参数仍要各就各位。"""
    for ext, kw in (("jpg", {"quality": 90}), ("png", {"quality": 30}),
                    ("tif", {"quality": 95}), ("webp", {"quality": 80})):
        out = write_file(_rgb(), str(tmp_path / f"m.{ext}"), **kw)
        assert out["skipped"] is False and out["bytes"] > 0
        img = Image.open(out["path"])
        assert img.size == (32, 24)
        assert img.info.get("icc_profile"), f"{ext} 没带上 ICC"


# ---------------------------------------------------------- 16-bit 母档也要同一套口径
#
# 为什么单独写这一组：8-bit 那条路上做了 ICC/冲突/原子，不代表直通那条也做了——
# 而 DoD-4 点的“16-bit RAW/TIFF 直通导出与批量队列稳定运行”恰恰走的是后者。
# 批量跑一百张时静默覆盖、或产出不带颜色档的母档，都是在最贵的那条路上坏掉。

def _u16(h=8, w=12):
    # 低 8 位全非零：免得夹具本身长得像“8-bit 左移补零”那张假 16-bit 图
    return (np.arange(h * w * 3, dtype=np.uint16).reshape(h, w, 3) * 7919 + 13).astype(np.uint16)


def test_tiff16_embeds_icc_and_the_tag_points_at_the_same_bytes(tmp_path):
    """嵌进去的档与 tag 偏移指向的字节必须逐字节相同，不是“有个条目”就算。"""
    from lumaretouch_engine.export import read_tiff16_icc, write_tiff16
    p = str(tmp_path / "m16.tif")
    want = _profile_bytes("srgb")
    info = write_tiff16(_u16(), p)
    assert info["icc_bytes"] == len(want) and info["skipped"] is False
    got = read_tiff16_icc(p)
    assert got == want, "ICC tag 指向的字节与递进去的不一致"
    # Pillow 也得真能把它当 ICC 读（只自写自读是循环论证）
    assert Image.open(p).info.get("icc_profile")


def test_tiff16_pixels_survive_the_icc_tag_insertion(tmp_path):
    """多了 588 字节的 ICC 后（实测值，不是估的），strip 偏移跟着走位，读回仍逐字节相等。

    这一条防的是“tag 加上了但偏移算错了”：那种文件能开、看着正常，
    而像素其实往右移了一段——只有读回对比能发现。
    """
    from lumaretouch_engine.export import read_tiff16, read_tiff16_icc, write_tiff16
    a = _u16()
    p = str(tmp_path / "pix.tif")
    write_tiff16(a, p)
    assert np.array_equal(read_tiff16(p), a), "带 ICC 的 16-bit 产物读回不等"
    # 不嵌时也得同样对（offset 不能假设 ICC 一定在场）
    q = str(tmp_path / "raw.tif")
    info = write_tiff16(a, q, output_profile="none")
    assert info["icc_bytes"] == 0
    assert np.array_equal(read_tiff16(q), a)
    assert read_tiff16_icc(q) is None, "声明不嵌却留了个 ICC 条目"


def test_tiff16_never_overwrites_and_honours_recheck(tmp_path):
    from lumaretouch_engine.export import write_tiff16
    p = tmp_path / "b.tif"
    p.write_bytes(b"someone-elses-master")
    before = p.read_bytes()
    info = write_tiff16(_u16(), str(p))
    assert info["skipped"] is True and info["bytes"] == 0
    assert p.read_bytes() == before, "skip 却动了已有母档"
    info2 = write_tiff16(_u16(), str(p), conflict_policy="recheck")
    assert info2["skipped"] is False and info2["renamed_from"] == str(p)
    assert p.read_bytes() == before, "recheck 把原件改了"
    with pytest.raises(ExportError, match="conflict_policy"):
        write_tiff16(_u16(), str(tmp_path / "c.tif"), conflict_policy="overwrite")


def test_tiff16_gps_switch_refuses_instead_of_going_silent(tmp_path):
    """未接通的功能必须拒并说原因。默默接受一个开了却不写 GPS 的开关，
    等于在用户面前把“隐私保护”变成了一个不起作用的控件。"""
    from lumaretouch_engine.export import write_tiff16
    with pytest.raises(ExportError, match="尚未实现"):
        write_tiff16(_u16(), str(tmp_path / "gps.tif"), metadata_include_gps=True)
    # 而默认（关）是结构性成立：产物里根本不会有 EXIF/GPS IFD
    p = str(tmp_path / "nogps.tif")
    info = write_tiff16(_u16(), p)
    assert info["gps_written"] is False and info["exif_bytes"] == 0


def test_tiff16_commit_is_atomic_and_leaves_no_temp(tmp_path, monkeypatch):
    from lumaretouch_engine.export import write_tiff16
    write_tiff16(_u16(), str(tmp_path / "a.tif"))
    assert [f.name for f in tmp_path.iterdir()] == ["a.tif"], "目录里留了临时文件"
    monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk gone")))
    with pytest.raises(OSError):
        write_tiff16(_u16(), str(tmp_path / "b.tif"))
    assert sorted(f.name for f in tmp_path.iterdir()) == ["a.tif"], "失败后留下现场"


# ---------------------------------------------------------- 方向标与“透传不能弄丢别的”

def test_orientation_is_dropped_because_pixels_are_already_upright(tmp_path):
    """COLOR-003 最后半句：“输出无二次方向错误”。

    解码层已经按 orientation 把像素摆正了，再把 274 透传出去就是让读方再转一次。
    这一条不是防微小差异：它直接决定导出的竖构图会不会躺下。
    """
    p = str(tmp_path / "orient.jpg")
    info = write_file(_rgb(), p, source_exif=_gps_exif(orient=6))
    assert info["orientation_dropped"] is True and info["exif_bytes"] > 0
    ex = Image.open(p).getexif()
    assert 0x0112 not in ex, f"方向标还跟着出去：orientation={ex[0x0112]}"
    assert ex[0x010E] == "contact@example.invalid", "删方向标时把别的字段一起弄丢了"


def test_gps_off_keeps_the_exif_sub_ifd(tmp_path):
    """只删要删的那一个。拍摄时间住在 Exif 子 IFD 里，它的指针是一个偏移量：
    处理不好要么一起丢，要么留下一个指向旧字节块的悬空偏移。"""
    p = str(tmp_path / "keep.jpg")
    write_file(_rgb(), p, source_exif=_gps_exif())
    ex = Image.open(p).getexif()
    sub = ex.get_ifd(0x8769)
    assert sub.get(0x9003) == "2026:10:18 09:00:01", f"拍摄时间没了：{dict(sub)}"
    assert not ex.get_ifd(0x8825)


def test_corrupt_source_exif_is_reported_not_swallowed(tmp_path):
    """COLOR-002：“展示…错误”。拿损坏的元数据当“没有”是最容易漏掉的一条静默降级。"""
    with pytest.raises(ExportError, match="解析失败"):
        write_file(_rgb(), str(tmp_path / "bad.jpg"), source_exif=b"Exif\x00\x00\xff" * 30)


def test_source_profile_passes_through_the_real_bytes(tmp_path):
    """output_profile=source 递的是源自己那份，不是重新生成一份 sRGB。"""
    want = _profile_bytes("srgb")
    p = str(tmp_path / "src.jpg")
    info = write_file(_rgb(), p, output_profile="source", source_icc=want)
    assert info["icc_bytes"] == len(want)
    assert Image.open(p).info.get("icc_profile") == want, "透传变成了重写"


# ---------------------------------------------------------- tiff_compression（注册表中性 deflate）

def test_tiff_compression_honours_the_registry_enum(tmp_path):
    sizes = {}
    for name in ("none", "deflate", "lzw"):
        info = write_file(_rgb(64, 64), str(tmp_path / f"c_{name}.tif"), tiff_compression=name)
        assert info["skipped"] is False and info["tiff_compression"] == name
        sizes[name] = info["bytes"]
        # 三种都要能读回来且像素不变：压缩参数不能把产物写成只有自家读得懂的东西
        assert np.array_equal(np.asarray(Image.open(info["path"]).convert("RGB")), _rgb(64, 64))
    assert sizes["none"] > max(sizes["deflate"], sizes["lzw"]), sizes


def test_default_tiff_compression_is_deflate_not_the_old_lzw(tmp_path):
    """中性位得按冻结的注册表来：不传参数时产物里的压缩算法要真是 deflate。"""
    p = str(tmp_path / "d.tif")
    info = write_file(_rgb(64, 64), p)
    assert info["tiff_compression"] == "deflate", info
    # 反查文件自己怎么说：TIFF tag 259(Compression) 必须是 8(Deflate)。报 deflate
    # 而文件头写的是 5(LZW) 或 1(无压缩)，就是清单与产物两张皮
    assert Image.open(p).tag_v2[259] == 8, Image.open(p).tag_v2[259]


def test_unknown_tiff_compression_is_rejected(tmp_path):
    with pytest.raises(ExportError, match="tiff_compression"):
        write_file(_rgb(), str(tmp_path / "z.tif"), tiff_compression="zip")


def test_builtin_srgb_profile_is_frozen_within_the_process():
    """同一进程里反复取 srgb 档必须拿到同一份字节。

    littleCMS 把建档那一刻的秒写进 profile 头部（第六个 uint16），不冻的话一次
    批量导出里每张图嵌的都是自己那一秒的档：同参数的两个产物字节不同，于是
    “重试固定输入”“冲突跳过后内容一致”这类逐字节判据全部立不住。这条是本轮
    端到端用例响出来之后补的门。
    """
    a = _profile_bytes("srgb")
    b = _profile_bytes("srgb")
    assert a == b and a is b
    time.sleep(1.1)                       # 走秒：不冻就会变
    assert _profile_bytes("srgb") == a
    # 内容仍是 sRGB built-in（不是“名字对了、字节是另一回事”）：头部的 colour space
    # 与 profile class 都该是 rgmt / mntr
    assert a[16:20] == b"RGB " and a[20:24] == b"XYZ ", a[16:24]
