"""Repair recipes must survive every version or fail before state/file mutation."""
import copy
import json

import numpy as np
import pytest

from lumaretouch_engine import project as P
from lumaretouch_engine import white_balance_recipe as WB
from lumaretouch_engine.repair_record import RepairOp, check_repair_fields, validate_repair_ops


def patch_params():
    return {"version": "source-patch-v1", "polygon": [[.6, .3], [.8, .3], [.8, .6], [.6, .6]],
            "offset": [-.4, 0.]}


def fixture(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source bytes stay untouched")
    project = P.new_project("repair", str(tmp_path))
    weight = np.arange(120, dtype=np.uint8).reshape(10, 12)
    heal = RepairOp(1, weight)
    patch = RepairOp(2, weight.copy(), patch_params(), kind="source_patch")
    recipe = {"_repair_ops": [heal, patch], "_redo_ops": [copy.deepcopy(patch)], "_proxy": (10, 12)}
    P.add_doc(project, str(source), recipe, version_id="live")
    return project, source, tmp_path / "repair.json"


def fields(project, stack="_repair_ops", index=1):
    return project["docs"][0]["versions"][0]["recipe"][stack][index]["fields"]


def test_mixed_records_and_redo_roundtrip_with_independent_parameters(tmp_path):
    project, source, path = fixture(tmp_path)
    before = source.read_bytes()
    P.save(project, str(path))
    loaded = P.load(str(path))
    assert loaded["schema_version"] == "lrt.project.v4"
    recipe, dropped = P.active_recipe(loaded, str(source))
    assert not dropped and source.read_bytes() == before
    assert [op.kind for op in recipe["_repair_ops"]] == ["heal", "source_patch"]
    assert recipe["_redo_ops"][0].params == patch_params()
    np.testing.assert_array_equal(recipe["_repair_ops"][1].weight, np.arange(120, dtype=np.uint8).reshape(10, 12))
    recipe["_repair_ops"][1].params["polygon"][0][0] = .9
    recipe["_repair_ops"][1].weight[:] = 0
    again, _ = P.active_recipe(loaded, str(source))
    assert again["_repair_ops"][1].params == patch_params()
    assert again["_repair_ops"][1].weight.any()
    assert recipe["_redo_ops"][0].params == patch_params()


@pytest.mark.parametrize("schema", [P.LEGACY_SCHEMA, P.WB_SCHEMA])
def test_legacy_missing_kind_migrates_to_heal_without_mutating_caller(tmp_path, schema):
    project, source, path = fixture(tmp_path)
    project["schema_version"] = schema
    recipe = project["docs"][0]["versions"][0]["recipe"]
    recipe["_repair_ops"] = recipe["_repair_ops"][:1]
    recipe["_redo_ops"] = [copy.deepcopy(recipe["_repair_ops"][0])]
    for key in ("_repair_ops", "_redo_ops"):
        del recipe[key][0]["fields"]["kind"]
    if schema == P.LEGACY_SCHEMA:
        del recipe["_wb_options"]
    before = copy.deepcopy(project)
    path.write_text(json.dumps(project))
    loaded = P.load(str(path))
    assert loaded["schema_version"] == P.SCHEMA
    decoded, dropped = P.active_recipe(loaded, str(source))
    assert not dropped
    assert decoded["_wb_options"] == WB.default_options()
    assert decoded["_repair_ops"][0].kind == decoded["_redo_ops"][0].kind == "heal"
    P.save(project, str(path))
    assert project == before
    assert json.loads(path.read_text())["schema_version"] == P.SCHEMA


@pytest.mark.parametrize("schema", [P.WB_SCHEMA, P.SCHEMA])
def test_v2_and_v3_both_require_white_balance_options(tmp_path, schema):
    project, _, path = fixture(tmp_path)
    project["schema_version"] = schema
    del project["docs"][0]["versions"][0]["recipe"]["_wb_options"]
    with pytest.raises(P.ProjectError, match="white-balance"):
        P.save(project, str(path))


@pytest.mark.parametrize("schema", [P.LEGACY_SCHEMA, P.WB_SCHEMA, P.SCHEMA])
@pytest.mark.parametrize("bad", ["kind", "version", "params", "missing_weight", "asset", "dtype", "shape", "hash", "bytes", "unknown_record"])
def test_bad_inactive_repair_records_reject_all_project_versions(tmp_path, schema, bad):
    project, _, path = fixture(tmp_path)
    P.save(project, str(path))
    original = path.read_bytes()
    project["schema_version"] = schema
    row = project["docs"][0]
    inactive = copy.deepcopy(row["versions"][0])
    inactive["id"] = "inactive"
    row["versions"].append(inactive)
    record = inactive["recipe"]["_redo_ops"][0]
    f = record["fields"]
    asset = project["assets"][f["weight"]["__asset__"]]
    if bad == "kind": f["kind"] = "new-unknown-kind"
    elif bad == "version": f["params"]["version"] = "source-patch-v999"
    elif bad == "params": f["params"]["offset"][0] = float("nan")
    elif bad == "missing_weight": del f["weight"]
    elif bad == "asset": del project["assets"][f["weight"]["__asset__"]]
    elif bad == "dtype": asset["dtype"] = "float32"
    elif bad == "shape": asset["shape"] = [12, 10]
    elif bad == "hash": asset["b64"] = "AAAA"
    elif bad == "bytes": asset["bytes"] += 1
    elif bad == "unknown_record": record["__dc__"] = "FutureRepair"
    with pytest.raises(P.ProjectError):
        P.save(project, str(path))
    assert path.read_bytes() == original
    path.write_text(json.dumps(project))
    with pytest.raises(P.ProjectError):
        P.load(str(path))


def test_v3_missing_kind_and_wrong_proxy_dimensions_are_not_migrated(tmp_path):
    project, _, _ = fixture(tmp_path)
    bad = copy.deepcopy(project)
    del fields(bad)["kind"]
    with pytest.raises(P.ProjectError): P.validate(bad)
    bad = copy.deepcopy(project)
    bad["docs"][0]["versions"][0]["recipe"]["_proxy"] = [12, 10]
    with pytest.raises(P.ProjectError): P.validate(bad)


def test_repair_encode_failures_do_not_append_dropped_or_change_project(tmp_path, monkeypatch):
    project, source, _ = fixture(tmp_path)
    before = copy.deepcopy(project)
    bad = RepairOp(3, np.ones((10, 12), np.uint8), patch_params(), "source_patch")
    bad.params["version"] = "unknown"
    with pytest.raises(P.ProjectError):
        P.add_doc(project, str(source), {"_repair_ops": [bad]}, version_id="live")
    assert project == before
    bad.params = patch_params()
    monkeypatch.setattr(P, "MAX_ASSET_BYTES", 1)
    with pytest.raises(P.ProjectError, match="data loss"):
        P.add_doc(project, str(source), {"_repair_ops": [bad]}, version_id="live")
    assert project == before


def test_direct_decode_cannot_drop_unknown_repair_or_missing_coverage(tmp_path):
    project, _, _ = fixture(tmp_path)
    value = project["docs"][0]["versions"][0]["recipe"]
    value["_repair_ops"][0]["__dc__"] = "FutureRepair"
    dropped = []
    with pytest.raises(P.ProjectError): P.decode(value, project["assets"], dropped, "recipe")
    assert dropped == []


def test_record_validator_does_not_coerce_kind_weight_or_bad_fields():
    valid = RepairOp(1, np.zeros((2, 3), np.uint8))
    clean = check_repair_fields({k: v for k, v in vars(valid).items() if k != "kind"})
    assert clean["kind"] == "heal"
    for key, value in (("kind", None), ("kind", "unknown"), ("op_id", True),
                       ("weight", np.zeros((2, 3), np.float32)), ("params", {"pad": float("inf")})):
        bad = copy.deepcopy(valid)
        setattr(bad, key, value)
        with pytest.raises(ValueError): validate_repair_ops([bad])
    valid.extra = 1
    with pytest.raises(ValueError): validate_repair_ops([valid])
