"""作用域名单与冻结注册表的一致性（PRESET/BATCH 的"唯一出处"守卫，不需要 torch）。

为什么要单独立一份文件：`scope.MODULES` 与 `docs/p0/p0-registry-frozen.json` 是两份东西，
一份在运行时（进 deb），一份在仓库里（判据）。它们一旦漂：注册表新加一个模块而代码不认，
预设/批量会把它整条拒（用户看到"未知模块"）；反过来代码里有而注册表没有，就是**凭空多出
的控件**。两种都难在真机上复查，所以在这里双向对拍。

判据落在"名单 + 中性值 + 量程"三件事上，不落在描述文字上。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lumaretouch_engine import scope as SC

REPO = Path(__file__).resolve().parents[2]
REG = json.loads((REPO / "docs" / "p0" / "p0-registry-frozen.json").read_text(encoding="utf-8"))


def reg_entry(op_id: str, key: str) -> dict:
    for e in REG["entries"]:
        if e["operation_id"] == op_id and e["parameter_key"] == key:
            return e
    raise AssertionError(f"冻结注册表里没有 {op_id}.{key}：判据失去了唯一出处")


def test_module_names_are_exactly_the_registry_operations_we_claim():
    """`scope.MODULES` 的键必须逐个能在冻结注册表里找到同一个 operation_id。"""
    reg_ops = {e["operation_id"] for e in REG["entries"]}
    missing = [op for op in SC.known_ops() if op not in reg_ops]
    assert not missing, f"代码里有注册表不认的模块（凭空控件）：{missing}"


@pytest.mark.parametrize("op", sorted(SC.known_ops()))
def test_every_registry_parameter_is_modeled_or_recorded_as_unmodeled(op):
    """代码声明的每个参数键都要是注册表里那一条；反向也要。

    反向那一半不能一律要求“都建模”：本版本确实有没接通的参数（保护痣/斑、蒙版羽化）。
    但它**必须被记在 unmodeled 里并带原因**：写了原因才会整条拒并告诉用户为什么，
    没写就会“静默丢掉一个参数”——那是假绿。UI 也直接拿这张表把控件禁用并说明理由。
    """
    reg_keys = {e["parameter_key"] for e in REG["entries"] if e["operation_id"] == op}
    declared = set(SC.MODULES[op]["params"])
    invented = declared - reg_keys
    assert not invented, f"{op} 声明了注册表里没有的参数（凭空控件）：{sorted(invented)}"
    unmodeled = reg_keys - declared
    for k in sorted(unmodeled):
        why = SC.unmodeled_reason(op, k)
        assert why, f"{op}.{k} 在注册表里而代码没建模，又没写原因：会被静默丢掉"
        assert len(why) > 8, f"{op}.{k} 的“为什么”是空话：{why!r}"


def test_enabled_is_an_alias_of_strength_not_a_second_switch():
    """`enabled` 不单独存一格（scope 的模块 docstring 第 1 条）。

    注册表给了 enabled 与 strength 两个键，而引擎只有一位强度：`enabled` 只能是
    "strength > 0" 的只读别名。这条守卫保证我们不会哪天又加出一个独立开关，
    造出 `enabled=1 且 strength=0` 那种"开着但没作用"的自相矛盾配方。
    """
    st = {"_exposure": (0.0, 0.0, 0.0), "_crop_rect": (0.0, 0.0, 1.0, 1.0),
          "_crop_rotation": 0.0, "_strength": 0.4}
    assert SC.MODULES[SC.OP_SKIN]["read"](st)["enabled"] is True
    off = SC.apply_modules(st, {SC.OP_SKIN: {"enabled": False}})
    assert off["_strength"] == 0.0, "enabled=False 没把强度归零：那就是两位开关在互相打脸"
    on = SC.apply_modules(st, {SC.OP_SKIN: {"strength": 0.7}})
    assert SC.MODULES[SC.OP_SKIN]["read"](on)["enabled"] is True


@pytest.mark.parametrize("op,key,expect", [
    (SC.OP_EXPOSURE, "ev", 0.0),
    (SC.OP_WHITE_BALANCE, "temperature_shift", 0.0),
    (SC.OP_WHITE_BALANCE, "tint_shift", 0.0),
    (SC.OP_CROP, "rotation_degrees", 0.0),
    (SC.OP_SKIN, "strength", 0.0),
    (SC.OP_BLEMISH, "strength", 0.0),
])
def test_neutral_values_match_the_frozen_registry(op, key, expect):
    """中性值逐条对冻结件：这里写"我觉得的 0"没有意义，注册表说了算。"""
    assert float(reg_entry(op, key)["neutral"]) == pytest.approx(expect)
    assert SC._neutral_of(op, key) == pytest.approx(expect)


def test_crop_neutral_rect_matches_registry():
    r = reg_entry(SC.OP_CROP, "rect_normalized")["neutral"]
    assert [float(x) for x in r] == [float(x) for x in SC.NEUTRAL_RECT], \
        "裁剪中性框与冻结件不同：预设会把'不裁剪'解释成另一个框"


@pytest.mark.parametrize("op,key", [(SC.OP_EXPOSURE, "ev"), (SC.OP_WHITE_BALANCE, "temperature_shift"),
                                    (SC.OP_WHITE_BALANCE, "tint_shift"),
                                    (SC.OP_CROP, "rotation_degrees"), (SC.OP_SKIN, "strength")])
def test_hard_ranges_agree_with_the_registry(op, key):
    """量程也对拍：`check_params` 卡的范围必须是冻结件那一个。

    代码里的 RANGE_* 比注册表窄 → 合法参数被拒；比它宽 → 越界值进了引擎，后面只能靠
    库层兜（而库层兜不住的那个下场，ADR-0003 里记着 eps=0 的 NaN 事故）。
    """
    r = reg_entry(op, key)["range"]
    lo, hi = {"ev": SC.RANGE_EV, "temperature_shift": SC.RANGE_TEMP, "tint_shift": SC.RANGE_TINT,
              "rotation_degrees": SC.RANGE_ROTATION, "strength": SC.RANGE_STRENGTH}[key]
    assert float(r["min"]) == pytest.approx(lo) and float(r["max"]) == pytest.approx(hi), \
        f"{op}.{key} 量程漂了：注册表 [{r['min']}, {r['max']}] vs 代码 [{lo}, {hi}]"


def test_batch_module_scope_values_are_the_registry_operation_ids():
    """`lnx.batch.v1.module_scope` 的类型写的是 `set[operation_id]`——所以合法值只能是
    注册表里那些 operation_id，而且空集不允许通过（冻结件原文）。"""
    e = reg_entry("lnx.batch.v1", "module_scope")
    assert e["type"] == "set[operation_id]"
    assert e["neutral"] == [], "冻结件的中性就是空集；判据得按这份写"
    assert "非空" in (e["reason"] or "") or "非空" in json.dumps(e, ensure_ascii=False), \
        "冻结件里'空集不允许通过 preflight'这句话没被读到，守卫要重找依据"
    with pytest.raises(SC.ScopeError):
        SC.check_scope([])
    with pytest.raises(SC.ScopeError):
        SC.check_scope(["lnx.not-a-real-op.v1"])


def test_conflict_policy_has_no_overwrite_option():
    """注册表的 conflict_policy 枚举里两个都是**不覆盖**：出现 overwrite 就是违约。"""
    e = reg_entry("lnx.batch.v1", "conflict_policy")
    assert set(e["enum"]) == {"skip_and_report", "recheck"}, e["enum"]


def test_mask_module_is_declared_untransferable_with_a_reason():
    """未接通的东西必须有原因，而且要在数据里（不是只在注释里）——UI 直接读它。"""
    m = SC.MODULES[SC.OP_MASK]
    assert m["transferable"] is False
    assert m["why_not"] and len(m["why_not"]) > 8, "禁用原因是空话：要能解释'为什么没接通'"
    with pytest.raises(SC.ScopeError):
        SC.check_scope([SC.OP_MASK])
    with pytest.raises(SC.ScopeError):
        SC.check_params(SC.OP_MASK, {"feather": 2})
