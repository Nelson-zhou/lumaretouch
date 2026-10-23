"""UNRUN: authored virtual-copy v23 contracts; no execution was authorized.

Fixtures provide fingerprints so project metadata operations do not read or write
source photos. Tests write only project JSON when explicitly checking round trips.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

from lumaretouch_engine import project as P
from lumaretouch_engine import virtual_copy_storage as VC


def _fp(path, data=b"immutable-source"):
    digest = hashlib.sha256(data).hexdigest()
    return {"path": str(path), "bytes": len(data), "sha256": digest,
            "head_sha256": digest, "hash_level": "full", "mtime_ns": 10,
            "readonly": True}


def _project(tmp_path):
    project = P.new_project("virtual copies", str(tmp_path))
    path = str(tmp_path / "source.raw")
    row = P.add_doc(project, path, None, fp=_fp(path), version_id="live")
    return project, row


def _legacy_v22(tmp_path):
    project, _ = _project(tmp_path)
    project["schema_version"] = P.COLOUR_EDITOR_SCHEMA
    project.pop("source_assets")
    for row in project["docs"]:
        for key in ("document_id", "source_asset_id", "root_document_id", "copy_number",
                    "recipe_version_id"):
            row.pop(key)
    return project


def test_v22_identity_migration_is_deterministic_and_does_not_edit_versions(tmp_path):
    legacy = _legacy_v22(tmp_path)
    versions = copy.deepcopy(legacy["docs"][0]["versions"])
    first, second = P._migrate(legacy), P._migrate(legacy)
    assert first["schema_version"] == "lrt.project.v23"
    for key in ("document_id", "source_asset_id", "root_document_id", "recipe_version_id"):
        assert first["docs"][0][key] == second["docs"][0][key]
    assert first["docs"][0]["versions"] == versions
    assert legacy["docs"][0]["versions"] == versions
    assert "document_id" not in legacy["docs"][0]
    row = first["docs"][0]
    source = first["source_assets"][row["source_asset_id"]]
    assert source["fingerprint_aliases"] == [row["fingerprint"]["sha256"]]


def test_v22_feature_validator_remains_enabled(tmp_path, monkeypatch):
    from lumaretouch_engine import colour_editor_adapters
    legacy = _legacy_v22(tmp_path)
    allowed_values = []

    def record_allowed(value, *, allowed=True):
        allowed_values.append(allowed)

    monkeypatch.setattr(colour_editor_adapters, "validate_records", record_allowed)
    P.validate(legacy)
    P.validate(P._migrate(legacy))
    assert allowed_values and all(allowed_values)


def test_legacy_duplicate_paths_still_reject_instead_of_deduplicating(tmp_path):
    legacy = _legacy_v22(tmp_path)
    legacy["docs"].append(copy.deepcopy(legacy["docs"][0]))
    with pytest.raises(P.ProjectError, match="path"):
        P.validate(legacy)


def test_legacy_identical_bytes_at_distinct_paths_stay_distinct(tmp_path):
    legacy = _legacy_v22(tmp_path)
    second = copy.deepcopy(legacy["docs"][0])
    second["path"] = str(tmp_path / "independent.raw")
    second["fingerprint"]["path"] = second["path"]
    legacy["docs"].append(second)
    migrated = P._migrate(legacy)
    assert len(migrated["source_assets"]) == 2
    assert migrated["docs"][0]["source_asset_id"] != migrated["docs"][1]["source_asset_id"]


def test_v23_missing_identity_is_corrupt_not_silently_repaired(tmp_path):
    project, row = _project(tmp_path)
    row.pop("document_id")
    with pytest.raises(P.ProjectError, match="document_id"):
        P.validate(project)


def test_same_path_is_legal_only_for_explicit_same_source_copy(tmp_path):
    project, root = _project(tmp_path)
    child = P.add_doc(project, root["path"], None, fp=root["fingerprint"],
                      document_id="copy-document", source_asset_id=root["source_asset_id"],
                      root_document_id=root["document_id"], copy_number=1,
                      recipe_version_id="copy-recipe", version_id="live")
    assert len(project["docs"]) == 2
    assert child["document_id"] != root["document_id"]
    P.validate(project)
    with pytest.raises(P.ProjectError, match="Ambiguous"):
        P.find_doc(project, root["path"])
    assert P.find_doc(project, document_id=child["document_id"]) is child
    assert P.active_recipe(project, document_id=child["document_id"]) == (None, [])


def test_unlinked_same_path_add_is_rejected_atomically(tmp_path):
    project, root = _project(tmp_path)
    before = copy.deepcopy(project)
    with pytest.raises(P.ProjectError):
        P.add_doc(project, root["path"], None, fp=root["fingerprint"],
                  document_id="unlinked-root", source_asset_id="another-source",
                  root_document_id="unlinked-root", recipe_version_id="another-recipe")
    assert project == before


def test_explicit_id_save_retains_all_identities_and_only_updates_that_row(tmp_path):
    project, root = _project(tmp_path)
    child = VC.create_copy(project, root["document_id"])
    child_before = copy.deepcopy(child)
    identity_before = {key: root[key] for key in
                       ("document_id", "source_asset_id", "root_document_id", "recipe_version_id")}
    P.add_doc(project, root["path"], None, fp=root["fingerprint"],
              document_id=root["document_id"], version_id="live", tags=["root-only"])
    assert child == child_before
    assert {key: root[key] for key in identity_before} == identity_before
    assert root["tags"] == ["root-only"]


def test_copy_is_deep_and_keeps_nested_source_provenance_unchanged(tmp_path):
    project, root = _project(tmp_path)
    root["versions"][0]["recipe"] = {
        "source_asset_id": "historic-render-source", "nested": {"source_path": "/old/location"}}
    root["undo_history"] = [{"retained": [1, 2]}]
    root["redo_history"] = [{"retained": [3]}]
    root["document_history"] = {"undo": [{"tag": "original"}], "redo": []}
    root["document_revision"] = 42
    child = VC.create_copy(project, root["document_id"])
    assert child["versions"] == root["versions"]
    assert child["recipe_version_id"] != root["recipe_version_id"]
    assert child["undo_history"] == child["redo_history"] == []
    assert child["document_history"] == {"undo": [], "redo": []}
    assert child["document_revision"] == 0 and root["document_revision"] == 42
    child["versions"][0]["recipe"]["nested"]["source_path"] = "/child-only"
    assert root["versions"][0]["recipe"]["nested"]["source_path"] == "/old/location"
    assert root["undo_history"] == [{"retained": [1, 2]}]


def test_copy_of_copy_belongs_to_root_and_numbers_do_not_reuse_trash(tmp_path):
    project, root = _project(tmp_path)
    first = VC.create_copy(project, root["document_id"])
    second = VC.create_copy(project, first["document_id"])
    VC.set_trashed(project, second["document_id"], True)
    third = VC.create_copy(project, first["document_id"])
    assert [first["copy_number"], second["copy_number"], third["copy_number"]] == [1, 2, 3]
    assert all(row["root_document_id"] == root["document_id"] for row in project["docs"])


def test_creation_with_an_explicit_copy_identity_is_idempotent(tmp_path):
    project, root = _project(tmp_path)
    child = VC.create_copy(project, root["document_id"], new_document_id="retry-safe-copy",
                           recipe_version_id="retry-safe-recipe")
    again = VC.create_copy(project, root["document_id"], new_document_id="retry-safe-copy",
                           recipe_version_id="retry-safe-recipe")
    assert again is child and len(project["docs"]) == 2


def test_root_trash_cascades_copy_trash_does_not_and_restore_is_selected(tmp_path):
    project, root = _project(tmp_path)
    first = VC.create_copy(project, root["document_id"])
    second = VC.create_copy(project, root["document_id"])
    assert VC.set_trashed(project, first["document_id"], True) == [first["document_id"]]
    assert not root["trashed"] and not second["trashed"]
    VC.set_trashed(project, root["document_id"], True)
    assert all(row["trashed"] for row in project["docs"])
    assert VC.set_trashed(project, root["document_id"], True) == []
    VC.set_trashed(project, first["document_id"], False)
    assert not root["trashed"] and not first["trashed"] and second["trashed"]
    assert VC.set_trashed(project, first["document_id"], False) == []
    VC.validate_identity(project)


def test_relocation_updates_all_rows_without_rewriting_recipe_provenance(tmp_path):
    project, root = _project(tmp_path)
    child = VC.create_copy(project, root["document_id"])
    root["versions"][0]["recipe"] = {"source_path": "/historical/recipe/path"}
    child["versions"][0]["recipe"] = {"source_asset_id": "historical-render-id"}
    versions = [copy.deepcopy(row["versions"]) for row in project["docs"]]
    source_id = root["source_asset_id"]
    new_path = str(tmp_path / "relocated.raw")
    VC.relocate_source(project, source_id, new_path, _fp(new_path))
    assert all(row["path"] == new_path for row in project["docs"])
    assert all(row["source_asset_id"] == source_id for row in project["docs"])
    assert [row["versions"] for row in project["docs"]] == versions
    VC.validate_identity(project)


def test_different_full_hash_never_becomes_an_alias(tmp_path):
    project, root = _project(tmp_path)
    before = copy.deepcopy(project)
    changed = copy.deepcopy(root["fingerprint"])
    changed["sha256"] = "a" * 64  # Same length/head; detects deeper content drift.
    with pytest.raises(ValueError, match="full fingerprint changed"):
        VC.register_source(project, root["source_asset_id"], root["path"], changed)
    assert project == before


def test_relocation_requires_matching_full_fingerprints(tmp_path):
    project, root = _project(tmp_path)
    before = copy.deepcopy(project)
    target = str(tmp_path / "other.raw")
    incoming = _fp(target)
    incoming["hash_level"] = "head"
    incoming["sha256"] = None
    with pytest.raises(ValueError, match="matching full"):
        VC.relocate_source(project, root["source_asset_id"], target, incoming)
    assert project == before


def test_duplicate_recipe_identity_and_orphan_copy_are_rejected(tmp_path):
    project, root = _project(tmp_path)
    child = VC.create_copy(project, root["document_id"])
    own_recipe = child["recipe_version_id"]
    child["recipe_version_id"] = root["recipe_version_id"]
    with pytest.raises(ValueError, match="Recipe identity"):
        VC.validate_identity(project)
    child["recipe_version_id"] = own_recipe
    project["docs"].remove(root)
    with pytest.raises(ValueError, match="missing root"):
        VC.validate_identity(project)


@pytest.mark.parametrize("revision", [-1, True, 1.5, VC.MAX_DOCUMENT_REVISION + 1])
def test_invalid_persisted_revision_is_rejected(tmp_path, revision):
    project, root = _project(tmp_path)
    root["document_revision"] = revision
    with pytest.raises(ValueError, match="document_revision"):
        VC.validate_identity(project)


def test_invalid_history_shape_and_oversized_identity_are_rejected(tmp_path):
    project, root = _project(tmp_path)
    root["document_history"] = {"undo": [], "redo": None}
    with pytest.raises(ValueError, match="document_history"):
        VC.validate_identity(project)
    root.pop("document_history")
    root["recipe_version_id"] = "x" * (VC.MAX_ID_LENGTH + 1)
    with pytest.raises(ValueError, match="recipe_version_id"):
        VC.validate_identity(project)


def test_project_save_load_retains_copy_identity_and_independent_histories(tmp_path):
    project, root = _project(tmp_path)
    child = VC.create_copy(project, root["document_id"])
    root["document_history"] = {"undo": [{"tag": "root"}], "redo": []}
    child["document_history"] = {"undo": [], "redo": [{"tag": "copy"}]}
    path = str(tmp_path / "copies.lrproject.json")
    P.save(project, path)
    loaded = P.load(path)
    assert loaded["docs"] == project["docs"]
    assert loaded["source_assets"] == project["source_assets"]
    assert P.find_doc(loaded, document_id=child["document_id"])["document_history"]["redo"] == [{"tag": "copy"}]
