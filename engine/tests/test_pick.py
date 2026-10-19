"""挑图度量层（LNX-PICK-001）的单测：全部是纯 numpy 的可复算判据，不需要 torch。

这一份为什么重要到要单独成文件：挑图的阈值就是**判据**，而判据最怕两种漂移——
①有人把阈值改成一个「看起来合理」的数（这里的每个数都由 packaging/pick-calibrate.py
在夹具上量出来，测试把它钉回实测方向）；②有人换一个缩放器/换一种归一化，于是同一张图
在两台机器上给出不同结论（那就是假滤镜只差一句注释）。

端到端那半（起引擎、发 pick analyze、看事件与磁盘）在 test_acceptance_p1.py，
因为它要真 FaceMesh 与真解码。
"""
from __future__ import annotations

import io
import os
import re

import numpy as np
import pytest
from PIL import Image, ImageFilter

from lumaretouch_engine import picks as PK

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "portrait-1024x1280.jpg")
DUAL = os.path.join(HERE, "fixtures", "portrait-dual-1570x950.jpg")


def _load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def _gauss(rgb: np.ndarray, r: float) -> np.ndarray:
    """标定台用的同一把尺：PIL 高斯模糊。阈值类断言必须钉在**标定台上量过的那些数**上，
    换成测试自造的模糊图，读数就落到另一个区间，测的就不是同一条判据了。
    """
    return np.asarray(Image.fromarray(rgb).filter(ImageFilter.GaussianBlur(r)),
                      dtype=np.uint8)


def _grad(h: int = 240, w: int = 320, seed: int = 3) -> np.ndarray:
    """一张有结构的「假照片」：低频底 + 随机块，高频能量足以过对比度下限。"""
    rng = np.random.default_rng(seed)
    base = np.add.outer(np.linspace(30, 210, h), np.linspace(20, 180, w)).astype(np.float32)
    blocks = rng.integers(0, 90, size=(h // 8, w // 8)).astype(np.float32)
    fine = np.repeat(np.repeat(blocks, 8, axis=0), 8, axis=1)[:h, :w]
    a = np.clip(base + fine, 0, 255)
    return np.dstack([a, a * 0.96, a * 0.9]).astype(np.uint8)


def _blur(rgb: np.ndarray, sigma: float) -> np.ndarray:
    """可分离高斯模糊（纯 numpy 移位加权，不引 PIL，测试环境与引擎环境同一套数学）。

    测试自己造「糊」这个事实而不调库：判据在测的是**相对关系**，两边都用同一条
    `picks.to_gray_measured` 的降采样口径，结论才可复算。
    """
    r = max(1, int(round(sigma * 3)))
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-(x ** 2) / (2.0 * sigma * sigma))
    k /= k.sum()
    a = rgb.astype(np.float32)
    h = a.shape[1]
    p = np.pad(a, ((0, 0), (r, r), (0, 0)), mode="edge")
    acc = np.zeros_like(a)
    for i in range(p.shape[1] - h + 1):
        acc += k[i] * p[:, i:i + h, :]
    hh = acc.shape[0]
    q = np.pad(acc, ((r, r), (0, 0), (0, 0)), mode="edge")
    out = np.zeros_like(a)
    for i in range(q.shape[0] - hh + 1):
        out += k[i] * q[i:i + hh, :, :]
    return np.clip(out, 0, 255).astype(np.uint8)


def _measures(rgb: np.ndarray, **kw) -> PK.Measures:
    cl = PK.clarity(rgb)
    under, over = PK.exposure_shares(rgb)
    m = PK.Measures(path=kw.pop("path", "/x/y.jpg"), dhash=PK.dhash64(rgb),
                    sharpness=cl["lapvar"], ratio=cl["ratio"], contrast=cl["contrast"],
                    under=under, over=over)
    for k, v in kw.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------- dHash 与分组
def test_dhash_ignores_light_tone_shift_and_splits_different_composition():
    """同一构图加 2 的偏置距离为 0；裁掉一条边是「另一格构图」，哈希必须远开。

    这两个方向都测，是因为只测一个就会把 dHash 写成「万能相似度量」：它对轻微调色稳，
    对构图变化敏感，而分组只在「稳」的那一侧有意义。标定台上实测：+2 偏置 0 位、
    裁 6 px 36 位。
    """
    a = _grad()
    near = np.clip(a.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    crop = np.ascontiguousarray(a[6:180, 4:300])
    h0, h1, h2 = PK.dhash64(a), PK.dhash64(near), PK.dhash64(crop)
    assert PK.hamming(h0, h1) == 0
    assert PK.hamming(h0, h2) > PK.DUPLICATE_SENSITIVITY["similar"]


def test_blurred_copy_stays_in_the_same_group():
    a = _grad()
    b = _blur(a, 1.6)
    assert PK.hamming(PK.dhash64(a), PK.dhash64(b)) <= PK.DUPLICATE_SENSITIVITY["standard"]


def test_group_duplicates_is_a_relation_closure_and_says_so():
    """A像B、B像C 而 A 与 C 不像时，三个仍在同一组——而 notes 必须把这件事说出来。

    这是手册 2127 行「相似分组不是绝对重复判定」落到代码上的形状：组可以给，
    措辞不能越过「像」。
    """
    items = [("a", 0b0000), ("b", 0b0001), ("c", 0b0011)]
    g = PK.group_duplicates(items, 1)
    assert len(g) == 1 and sorted(g[0]) == ["a", "b", "c"]
    assert PK.hamming(0b0000, 0b0011) > 1          # A 与 C 其实不像
    sug = PK.suggest(PK.Measures(path="a", contrast=0.2, sharpness=0.02, ratio=0.3),
                     group=["a", "b", "c"], is_leader=True, rank_in_group=0, dup_bits=0)
    assert any("关系闭包" in n and "不是绝对重复" in n for n in sug["notes"])
    assert not any("删" in (r.get("text") or "") for r in sug["reasons"])


def test_single_item_does_not_form_a_group():
    assert PK.group_duplicates([("only", 1234)], 6) == []


# ---------------------------------------------------------------- 清晰度判据
def test_darkened_photo_is_not_called_blurry():
    """整体压暗 0.35× 后绝对能量比「明显糊」还低，而比值与真图同一格。

    这条是 clarity() 存在的全部理由（标定台实测：真图 0.011579/0.2996，压暗
    0.001417/0.2969，明显糊 0.005476/0.1444）。只看绝对值就会把一张曝光保守的好照片
    标成糊图——那是判据在冤枉用户。
    """
    a = _load(FIX)
    dark = np.clip(a.astype(np.float32) * 0.35, 0, 255).astype(np.uint8)
    soft = _gauss(a, 3.0)
    ca, cd, cs = PK.clarity(a), PK.clarity(dark), PK.clarity(soft)
    # 标定台实测锚点（夹具不动就不该漂；漂了说明度量口径变了，那要改注释里的出处）
    assert abs(ca["lapvar"] - 0.011579) < 5e-4 and abs(ca["ratio"] - 0.2996) < 0.01
    assert abs(cd["ratio"] - 0.2969) < 0.01
    assert abs(cs["ratio"] - 0.1444) < 0.01
    assert cd["lapvar"] < cs["lapvar"]                      # 绝对值：暗图比糊图还「糊」
    assert cd["ratio"] > ca["ratio"] * 0.75                 # 比值：暗图与真图同一格
    assert cs["ratio"] < ca["ratio"] * 0.75                 # 比值：糊图真的塌下去了
    assert PK.blur_read(_measures(dark), "strong", None) is None
    assert PK.blur_read(_measures(soft), "standard", None)["kind"] == "blur"


def test_flat_image_reports_inapplicable_instead_of_blurry():
    """纯色/平坦时清晰度判据不适用：不写「糊」，也不写「清晰」。

    实测两头都荒唐：纯色 graystd=0 ratio=0，纯色+噪声 graystd=0.00065 ratio=20.0。
    没有这条护栏，一张空白图会被判成糊图。
    """
    flat = np.full((200, 200, 3), 128, dtype=np.uint8)
    m = _measures(flat)
    br = PK.blur_read(m, "strong", None)
    assert br["kind"] == "flat"
    sug = PK.suggest(m, group=[m.path], is_leader=True, rank_in_group=0, dup_bits=None)
    assert "blur" not in sug["labels"] and "soft" not in sug["labels"]
    assert not any(r["kind"] == "flat" for r in sug["reasons"])   # 「不适用」不进建议


def test_batch_relative_line_catches_what_absolute_line_misses():
    """同批里明显更软的那一张由相对线抓（绝对能量没到线也要报，但只说「建议复核」）。

    跨图绝对值不可比（夹具实测两张真图的比值是 0.30 与 0.52），而挑图的真实场景就是
    「一批连拍里那张虚的」。
    """
    d = _load(DUAL)
    # 实测（同一夹具）：真图 0.5177/0.018002、+2 偏置 0.5177、糊 r=4.0 0.2319/0.007738。
    # 中位数 0.5177 → 相对线 0.2848 抓到 0.2319；而绝对线要 lapvar<0.006 且 ratio<0.16，
    # 0.007738 没到——**两条线各管各的那一段**，这才是"跨图不可比"的补丁长什么样。
    soft = _gauss(d, 4.0)
    ms = [_measures(d), _measures(np.clip(d.astype(np.int16) + 2, 0, 255).astype(np.uint8)),
          _measures(soft)]
    med = float(np.median([m.ratio for m in ms]))
    assert abs(med - 0.5177) < 0.01 and ms[2].ratio < med * PK.BLUR_REL_FACTOR["standard"]
    verdicts = [PK.blur_read(m, "standard", med) for m in ms]
    assert verdicts[2] is not None and verdicts[2]["kind"] == "soft_vs_batch"
    assert verdicts[0] is None and verdicts[1] is None
    sug = PK.suggest(ms[2], group=[ms[2].path], is_leader=True, rank_in_group=0,
                     dup_bits=None, batch_median_ratio=med)
    assert "soft" in sug["labels"] and "blur" not in sug["labels"]
    assert any(r["method"] == "clarity-ratio-vs-batch-median" and "建议复核" in r["text"]
               for r in sug["reasons"])


def test_exposure_clipping_direction_is_asymmetric():
    """欠曝看死黑占比、过曝看死白占比，两边各自过线；「偏暗」不算欠曝。"""
    a = _grad()
    dark = np.clip(a.astype(np.float32) * 0.35, 0, 255).astype(np.uint8)
    blown = np.clip(a.astype(np.float32) * 2.6 + 12, 0, 255).astype(np.uint8)
    assert PK.exposure_shares(a)[1] < PK.EXPOSURE_SENSITIVITY["strong"]
    assert PK.exposure_shares(blown)[1] > PK.EXPOSURE_SENSITIVITY["weak"]
    assert PK.exposure_shares(dark)[0] < PK.EXPOSURE_SENSITIVITY["strong"]   # 暗≠死黑
    sug = PK.suggest(_measures(blown), group=["p"], is_leader=True, rank_in_group=0,
                     dup_bits=None)
    assert "overexposed" in sug["labels"]
    r = next(x for x in sug["reasons"] if x["kind"] == "overexposed")
    assert "死白" in r["text"] and r["value"] > r["threshold"]


def test_measure_scale_is_aspect_safe_and_library_independent():
    """同一内容在竖构图与横构图上都落到长边 160：尺度是度量的公共前提。

    自己写降采样而不调 PIL 的理由写在 picks._downscale_mean 里（跨机器结论必须一致，
    且按步长抽样会混叠、把糊图读成锐图）。
    """
    tall = _grad(320, 200)
    wide = _grad(200, 320)
    gt, gw = PK.to_gray_measured(tall), PK.to_gray_measured(wide)
    assert max(gt.shape) == PK.MEASURE_EDGE and max(gw.shape) == PK.MEASURE_EDGE
    # 整数块均值（不是抽样）：把一张 2×2 方块图降下来，块均值给出真实占比
    chk = np.zeros((16, 16), dtype=np.float32)
    chk[:8, :] = 100.0
    out = PK._downscale_mean(chk, 4)
    assert out.shape == (4, 4)
    # 整数块均值给出**真实占比**：上半两格 100、下半两格 0。按步长抽样会得到 100,100,100,100
    # 或 0,0,0,0（取决于相位），那正是"混叠把糊图读成锐图"的那一族错
    assert np.allclose(out[:2], 100.0) and np.allclose(out[2:], 0.0)


# ---------------------------------------------------------------- 眼睑几何
def _lm_with_eye_geometry(w: int, h: int, gap_px: float, width_px: float) -> np.ndarray:
    """按**像素**摆出两只眼的关键点，再归一化（FaceMesh 的存储形状）。

    478 个槽位里只有眼睑/眼裂那 8 个点被读到，其余填 0 不影响量——但点数必须真的够
    478，因为「不够契约就返 None」也是判据的一部分。
    """
    lm = np.zeros((478, 3), dtype=np.float32)

    def put(idx: int, x: float, y: float) -> None:
        lm[idx, 0] = x / w
        lm[idx, 1] = y / h

    # 左眼：外眼角 (100,200)、内眼角 (100+width,200)；上/下睑中点在水平中线上按 gap 分
    cx, cy = 100.0 + width_px / 2.0, 200.0
    put(PK.EYE_LEFT["outer"], 100.0, cy)
    put(PK.EYE_LEFT["inner"], 100.0 + width_px, cy)
    put(PK.EYE_LEFT["upper"], cx, cy - gap_px / 2.0)
    put(PK.EYE_LEFT["lower"], cx, cy + gap_px / 2.0)
    # 右眼：同样的几何，放在 (300, 200) 起
    rx = 300.0
    put(PK.EYE_RIGHT["inner"], rx + width_px, cy)
    put(PK.EYE_RIGHT["outer"], rx, cy)
    put(PK.EYE_RIGHT["upper"], rx + width_px / 2.0, cy - gap_px / 2.0)
    put(PK.EYE_RIGHT["lower"], rx + width_px / 2.0, cy + gap_px / 2.0)
    return lm


@pytest.mark.parametrize("w,h", [(1024, 1280), (1570, 950), (640, 640)])
def test_eye_openness_measures_the_geometry_we_drew_in_pixels(w, h):
    """画进去 22 px 缝、40 px 眼裂 → 必须读出 0.55，与画布长宽比无关。

    这条就是量纲回归：归一化坐标直接开 hypot 时，同一个几何在 1024×1280 与 1570×950
    上会差一个 H/W（标定台上实测 0.370 与 0.754）。测试两个方向都测，是因为只测一个
    尺度的话「除错了分母」照样通过。
    """
    lm = _lm_with_eye_geometry(w, h, 22.0, 40.0)
    assert abs(PK.eye_openness(lm, image_size=(w, h)) - 0.55) < 1e-5


def test_eye_openness_takes_the_smaller_of_two_eyes():
    """被头发挡住一只眼时不能靠均值蒙过去：取小值。"""
    w, h = 800, 600
    lm = _lm_with_eye_geometry(w, h, 22.0, 40.0)
    # 左眼：上睑在 189、下睑原本 211（缝 22）。把下睑抬到 190 → 缝 1.5 px → 比 0.0375
    lm[PK.EYE_LEFT["lower"], 1] = 190.5 / h
    got = PK.eye_openness(lm, image_size=(w, h))
    assert abs(got - 1.5 / 40.0) < 1e-4                     # 读到的是那只小的，不是均值
    assert got < PK.eye_openness(_lm_with_eye_geometry(w, h, 22.0, 40.0), image_size=(w, h))


def test_eye_openness_refuses_to_guess_below_contract():
    """点数不够 478、眼角重合、尺寸非法一律 None：拿模板点阵量眼睑是一种伪装。"""
    w, h = 800, 600
    lm = _lm_with_eye_geometry(w, h, 22.0, 40.0)
    assert PK.eye_openness(lm[:400], image_size=(w, h)) is None
    assert PK.eye_openness(lm, image_size=(0, h)) is None
    flat = lm.copy()
    flat[PK.EYE_LEFT["inner"]] = flat[PK.EYE_LEFT["outer"]]
    assert PK.eye_openness(flat, image_size=(w, h)) is None


def test_suggest_never_claims_eyes_when_nothing_was_measured():
    """没量到眼睑时那一格只说「没量到」，既不写睁眼也不写闭眼（不许静默降级）。"""
    m = _measures(_grad(), eye_open=None, eye_note="")
    sug = PK.suggest(m, group=[m.path], is_leader=True, rank_in_group=0, dup_bits=None)
    assert "eyes_closed" not in sug["labels"]
    r = next(x for x in sug["reasons"] if x["kind"] == "eyes_unknown")
    assert r["value"] is None and "不写「睁眼」" in r["text"]
    m2 = _measures(_grad(), eye_open=None, eye_note="FaceMesh 后端不可用")
    sug2 = PK.suggest(m2, group=[m2.path], is_leader=True, rank_in_group=0, dup_bits=None)
    assert any("后端不可用" in (x.get("text") or "") for x in sug2["reasons"])


# ---------------------------------------------------------------- 建议的形状
def test_every_reason_is_recomputable_by_name():
    """每条原因都带 method / value / threshold：用户或下一个人能按名字复算。

    这是 DoD §2「严禁伪装 AI」在产品面上的兑现形状——功能名不重要，能不能被复核才重要。
    """
    a = _grad()
    m = _measures(_blur(a, 3.2), path="/x/soft.jpg", eye_open=0.09, faces=1)
    sug = PK.suggest(m, group=[m.path], is_leader=True, rank_in_group=0, dup_bits=None,
                     blur="strong", eyes="strong")
    assert sug["labels"]
    for r in sug["reasons"]:
        assert r.get("method") and "threshold" in r and "value" in r
        assert r.get("text")
    assert sug["overridable"] is True
    assert sug["auto_deleted"] is False and sug["auto_trashed"] is False


def test_user_mark_wins_and_suggestion_becomes_a_side_note():
    """已有用户标签/标记/回收站时：建议照旧报出（可覆盖），但标成被人工压过。"""
    m = _measures(_grad(), path="/x/a.jpg")
    plain = PK.suggest(m, group=[m.path], is_leader=True, rank_in_group=0, dup_bits=None)
    marked = PK.suggest(m, group=[m.path], is_leader=True, rank_in_group=0, dup_bits=None,
                        user_marked=True)
    assert plain["overridden_by_user"] is False
    assert marked["overridden_by_user"] is True and marked["overridable"] is True


def test_sensitivity_arms_move_the_line_and_are_reported():
    """同一份读数在三档下给出不同结论，而**用的哪一档跟着建议一起报出去**。

    数值取自标定台：明显糊 ratio 0.1444、轻糊 0.2633、真图 0.2996。
    """
    a = _load(FIX)
    soft = _measures(_gauss(a, 3.0))        # 实测 lapvar 0.005476 / ratio 0.1444
    sharp = _measures(a)                    # 实测 0.011579 / 0.2996
    assert PK.blur_read(soft, "weak", None) is None                     # 弱档只报最狠的
    assert PK.blur_read(soft, "standard", None)["kind"] == "blur"
    assert PK.blur_read(sharp, "strong", None) is None                  # 真图在三档都不挨
    sug = PK.suggest(soft, group=[soft.path], is_leader=True, rank_in_group=0,
                     dup_bits=None, blur="weak", eyes="strong", exposure="standard")
    assert sug["sensitivities"]["blur"] == "weak" and sug["sensitivities"]["eyes"] == "strong"


def test_thresholds_are_one_source_and_the_fingerprint_follows_them():
    """档位表只有一个出处，且阈值一动指纹就变（事件里能看出是哪一版量出来的）。"""
    t = PK.thresholds_for_json()
    assert t["blur_energy"] is not None and t["eyes"] == dict(PK.EYE_SENSITIVITY)
    fp0 = PK.fingerprint()
    saved = PK.EYE_SENSITIVITY["standard"]
    try:
        PK.EYE_SENSITIVITY["standard"] = saved + 0.001
        assert PK.fingerprint() != fp0
    finally:
        PK.EYE_SENSITIVITY["standard"] = saved
    assert PK.fingerprint() == fp0


def test_measures_serialization_carries_the_provenance_fields():
    """读数进 JSON 时把尺度、算法名、来源一起带走（RAW 相机预览必须看得见）。"""
    m = _measures(_grad(), decoded_from="camera_preview", decode_size=(512, 384), faces=2)
    j = m.for_json()
    assert j["measure_edge"] == PK.MEASURE_EDGE and j["algo"] == PK.ALGO_VERSION
    assert j["decoded_from"] == "camera_preview" and j["decode_size"] == [512, 384]
    assert j["faces"] == 2 and set(["sharpness", "clarity_ratio", "contrast"]) <= set(j)


# ── 宿主 env 桥的键名单守卫（这一条不是测挑图，是测「挑图能不能被点着」）────────
_ROOT = os.path.dirname(os.path.dirname(HERE))      # 仓根（engine/tests 往上两级）


def _ts_interface_keys(text: str, name: str) -> set:
    """取 `export interface <name> { … }` 里的字段名（跳过注释行）。"""
    m = re.search(r"export interface %s \{(.*?)\n\}" % name, text, re.S)
    assert m, f"没找到 interface {name}：前端那份声明改了写法，守卫要跟着改"
    body = m.group(1)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)      # JSDoc
    body = re.sub(r"//[^\n]*", "", body)                    # 行注释
    return {k for k in re.findall(r"^\s*(\w+)\??\s*:", body, re.M)}


def _rust_json_keys(text: str, fn: str) -> set:
    """取 `fn <name>` 里那个 `json!({ … })` 的键。按括号配对切段，不数行号。

    数行号的那版写法（取到下一个 `}` 所在行）会把 `json!` 里嵌的其它块当成结尾；
    这里从 `json!(` 那个左括号开始按深度配对，闭到深度归零的那一格。
    """
    i = text.index("fn %s(" % fn)
    j = text.index("json!(", i) + len("json!") - 1     # 停在左括号上
    depth = 0
    for k in range(j, len(text)):
        ch = text[k]
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
            if depth == 0:
                seg = text[j:k + 1]
                break
    else:
        raise AssertionError("json! 括号没配上，m0_env 的写法变了")
    return set(re.findall(r'"(\w+)":', seg))


def test_m0_env_bridge_returns_every_key_the_frontend_declares():
    """宿主 `m0_env` 返回的键必须与前端 `M0Env` 声明的字段**双向**一致。

    真实事故（1.6.0 那一轮 m5 第 7 臂）：TS 声明了 `auto_pick: string`，而 Rust 那份
    json! 里没这一格。TypeScript 全绿、`cargo check` 全绿、裸引擎端到端全绿，而装机壳
    里那条自动臂**一次都没点火**——因为 `env.auto_pick` 是 undefined，`if (env.auto_pick)`
    永远为假。JSON 边界上没有类型，编译期谁也抓不到谁；能抓的只有这一条名单双向比。

    方向两边都要查：前端多了→臂点不着（本轮）；宿主多了→前端读的是没声明的键，
    代码里写成 `?? null` 就当没事，下一轮删掉才知道根本没人读。
    """
    ts = io.open(os.path.join(_ROOT, "ui", "src", "native.ts"),
                 encoding="utf-8").read()
    rs = io.open(os.path.join(_ROOT, "ui", "src-tauri", "src", "main.rs"),
                 encoding="utf-8").read()
    declared = _ts_interface_keys(ts, "M0Env")
    returned = _rust_json_keys(rs, "m0_env")
    assert declared, "M0Env 一个字段都没解析出来——守卫本身失效了"
    missing = sorted(declared - returned)
    extra = sorted(returned - declared)
    assert not missing, (
        f"宿主 m0_env 没返回前端声明的这些键：{missing}。"
        "漏一条的表现是那条自动臂在真窗口里静默不点火（TS 不报错）")
    assert not extra, f"宿主 m0_env 多返回了前端没声明的键：{extra}（没人读的就删掉）"
    # 点名这一条：本轮就是它漏的，别让它在名单双向比之外还留一个盲点
    assert "auto_pick" in returned, "auto_pick 必须在宿主桥里（挑图那一臂的唯一点火口）"
