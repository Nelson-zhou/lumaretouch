"""Pure document/source identity storage for project v23.

No pixels, recipe provenance or source files are changed here. Logical identity is
not a content hash: even byte-identical independent imports remain independent.
"""
from __future__ import annotations

import copy
import os
import uuid

MAX_DOCUMENT_REVISION = (1 << 64) - 1
MAX_ID_LENGTH = 256


def _identifier(value, label, *, max_length=MAX_ID_LENGTH):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"Invalid {label}: expected a nonempty string up to {max_length} characters")
    return value


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def _full_hash(fp):
    if not isinstance(fp, dict) or fp.get("hash_level") != "full":
        return None
    digest = fp.get("sha256")
    if not _digest(digest):
        raise ValueError("A full source fingerprint needs a valid SHA-256")
    return digest


def _legacy_id(project_id, path, kind):
    # The separator prevents (project='ab', path='c') colliding with ('a', 'bc').
    # No filesystem lookup: reopening an unsaved legacy project is deterministic,
    # including when its source is offline or the project file has moved.
    name = f"lrt.project.v23\0{project_id}\0{path}\0{kind}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def _source_record(source_asset_id, path, fp):
    fingerprint = copy.deepcopy(fp) if isinstance(fp, dict) else {}
    if fingerprint:
        fingerprint["path"] = path
    digest = _full_hash(fingerprint)
    return {"source_asset_id": source_asset_id, "path": path,
            "fingerprint": fingerprint,
            "fingerprint_aliases": [digest] if digest else []}


def ensure_identity(project):
    """Add deterministic identity to owned legacy rows, without reading sources.

    This is a migration helper, not a permissive v23 loader. A saved v23 project
    must pass validate_identity before anything attempts to fill missing fields.
    Existing explicit IDs and nested recipes are never rewritten.
    """
    project_id = _identifier(project.get("project_id"), "project_id")
    sources = project.setdefault("source_assets", {})
    if not isinstance(sources, dict):
        raise ValueError("source_assets must be an object")
    for row in project["docs"]:
        path = row["path"]
        from .export_destination_import import origin
        row.setdefault('import_origin', origin(path, kind='legacy_parent'))
        row.setdefault("document_id", _legacy_id(project_id, path, "document"))
        row.setdefault("source_asset_id", _legacy_id(project_id, path, "source"))
        row.setdefault("root_document_id", row["document_id"])
        row.setdefault("copy_number", 0)
        row.setdefault("document_revision", 0)
        row.setdefault("recipe_version_id", _legacy_id(
            project_id, row["document_id"], "recipe"))
        source_id = row["source_asset_id"]
        if source_id not in sources:
            sources[source_id] = _source_record(source_id, path, row.get("fingerprint"))
    return project


def validate_identity(project):
    """Reject ambiguous, dangling or conflicting explicit document ownership."""
    sources = project.get("source_assets")
    if not isinstance(sources, dict):
        raise ValueError("Project v23 needs an authoritative source_assets object")
    documents, recipe_ids, copy_numbers, source_roots = {}, set(), set(), {}
    for index, row in enumerate(project["docs"]):
        if not isinstance(row, dict):
            raise ValueError(f"docs[{index}] must be an object")
        if "import_origin" in row:
            from .export_destination_import import validate
            validate(row["import_origin"])
        document_id = _identifier(row.get("document_id"), "document_id")
        source_id = _identifier(row.get("source_asset_id"), "source_asset_id")
        root_id = _identifier(row.get("root_document_id"), "root_document_id")
        recipe_id = _identifier(row.get("recipe_version_id"), "recipe_version_id")
        number = row.get("copy_number")
        if type(number) is not int or not 0 <= number <= 9007199254740991:
            raise ValueError("copy_number must be a JavaScript-safe nonnegative integer")
        revision = row.get("document_revision", 0)
        if type(revision) is not int or not 0 <= revision <= MAX_DOCUMENT_REVISION:
            raise ValueError("document_revision must be a bounded nonnegative integer")
        history = row.get("document_history")
        if "document_history" in row and (not isinstance(history, dict)
                or set(history) != {"undo", "redo"}
                or not isinstance(history["undo"], list)
                or not isinstance(history["redo"], list)):
            raise ValueError("document_history must contain separate undo and redo lists")
        if document_id in documents:
            raise ValueError(f"Duplicate document_id: {document_id}")
        if recipe_id in recipe_ids:
            raise ValueError(f"Recipe identity is shared between documents: {recipe_id}")
        if (root_id, number) in copy_numbers:
            raise ValueError(f"Duplicate copy_number {number} under {root_id}")
        if (number == 0) != (document_id == root_id):
            raise ValueError("Only the root document may have copy_number zero")
        if source_id in source_roots and source_roots[source_id] != root_id:
            raise ValueError("One logical source must belong to exactly one root")
        if source_id not in sources:
            raise ValueError(f"Missing authoritative source asset: {source_id}")
        documents[document_id] = row
        recipe_ids.add(recipe_id)
        copy_numbers.add((root_id, number))
        source_roots[source_id] = root_id
    paths = {}
    for source_id, source in sources.items():
        _identifier(source_id, "source asset key")
        if not isinstance(source, dict) or source.get("source_asset_id") != source_id:
            raise ValueError("Source asset key and source_asset_id disagree")
        path = _identifier(source.get("path"), "source path", max_length=32768)
        if path in paths and paths[path] != source_id:
            raise ValueError("A shared path requires an explicitly linked source asset")
        paths[path] = source_id
        fp, aliases = source.get("fingerprint"), source.get("fingerprint_aliases")
        if not isinstance(fp, dict):
            raise ValueError("Source fingerprint must be an object")
        if fp.get("path", path) != path:
            raise ValueError("Source fingerprint path differs from the source path")
        if (not isinstance(aliases, list) or any(not _digest(v) for v in aliases)
                or len(set(aliases)) != len(aliases)):
            raise ValueError("Source fingerprint aliases must be unique full SHA-256 values")
        digest = _full_hash(fp)
        if digest and digest not in aliases:
            raise ValueError("Authoritative full fingerprint is missing from its aliases")
    for row in documents.values():
        root = documents.get(row["root_document_id"])
        if root is None or root["root_document_id"] != root["document_id"]:
            raise ValueError("Virtual copy refers to a missing root or another copy")
        if root["source_asset_id"] != row["source_asset_id"]:
            raise ValueError("Virtual copy and root must own the same source asset")
        source = sources[row["source_asset_id"]]
        if row.get("path") != source["path"]:
            raise ValueError("Document path differs from its authoritative source")
        # Compatibility fingerprints may retain the older head-only level; they
        # must never contradict the authoritative evidence when both are present.
        row_fp = row.get("fingerprint") or {}
        if not isinstance(row_fp, dict):
            raise ValueError("Document fingerprint must be an object")
        _check_same_content(source["fingerprint"], row_fp)
        if not row.get("trashed", False) and root.get("trashed", False):
            raise ValueError("A live virtual copy cannot have a trashed root")


def _check_same_content(expected, actual):
    for key in ("bytes", "head_sha256"):
        if key == "bytes" and any(fp.get("bytes") == -1 and fp.get("hash_level") == "none" for fp in (expected, actual)): continue
        if (expected.get(key) is not None and actual.get(key) is not None
                and expected[key] != actual[key]):
            raise ValueError("Source content changed; refusing to rebind a logical source")
    old_hash, new_hash = _full_hash(expected), _full_hash(actual)
    if old_hash and new_hash and old_hash != new_hash:
        raise ValueError("Source full fingerprint changed; refusing to bless content drift")


def register_source(project, source_asset_id, path, fingerprint, *, relocate=False):
    """Register or verify a source; never replace its identity with a hash.

    Relocation is explicit and requires a full fingerprint, with the same known
    content. Lower-quality new evidence never downgrades a stored full hash.
    """
    _identifier(source_asset_id, "source_asset_id")
    path = os.path.abspath(str(path))
    if not isinstance(fingerprint, dict):
        raise ValueError("Source fingerprint must be an object")
    incoming = copy.deepcopy(fingerprint)
    incoming["path"] = path
    sources = project.setdefault("source_assets", {})
    source = sources.get(source_asset_id)
    for other_id, other in sources.items():
        if other_id != source_asset_id and other.get("path") == path:
            raise ValueError("Same-path documents must explicitly share a source asset")
    if source is None:
        source = _source_record(source_asset_id, path, incoming)
        sources[source_asset_id] = source
    else:
        if source["path"] != path and not relocate:
            raise ValueError("Source relocation must be explicit")
        expected = source["fingerprint"]
        _check_same_content(expected, incoming)
        old_hash, new_hash = _full_hash(expected), _full_hash(incoming)
        if source["path"] != path and (not old_hash or not new_hash):
            raise ValueError("Relocation needs matching full source fingerprints")
        aliases = list(source.get("fingerprint_aliases", []))
        if new_hash and aliases and new_hash not in aliases and old_hash is None:
            raise ValueError("Source fingerprint is not one of its retained full aliases")
        if new_hash and new_hash not in aliases:
            aliases.append(new_hash)
        if (old_hash and not new_hash) or (expected.get("hash_level") == "head" and incoming.get("hash_level") in (None,"none")):
            merged = copy.deepcopy(expected)
            merged["path"] = path
            for key in ("mtime_ns", "readonly"):
                if key in incoming:
                    merged[key] = incoming[key]
        else:
            merged = incoming
        source.update(path=path, fingerprint=merged, fingerprint_aliases=aliases)
    for row in project["docs"]:
        if row.get("source_asset_id") == source_asset_id:
            row["path"] = path
            row["fingerprint"] = copy.deepcopy(source["fingerprint"])
    return source


def relocate_source(project, source_asset_id, path, fingerprint):
    """Update one source and all linked rows after read-only full verification."""
    if source_asset_id not in project.get("source_assets", {}):
        raise ValueError(f"Unknown source asset: {source_asset_id}")
    return register_source(project, source_asset_id, path, fingerprint, relocate=True)


def create_copy(project, document_id, *, new_document_id=None, recipe_version_id=None):
    """Deep-copy owned metadata/recipe without copying the source's bytes."""
    validate_identity(project)
    parent = next((r for r in project["docs"] if r["document_id"] == document_id), None)
    if parent is None:
        raise ValueError(f"Unknown document: {document_id}")
    if new_document_id is not None:
        existing = next((r for r in project["docs"] if r["document_id"] == new_document_id), None)
        if existing is not None:
            if (existing["copy_number"] == 0
                    or existing["root_document_id"] != parent["root_document_id"]
                    or existing["source_asset_id"] != parent["source_asset_id"]
                    or (recipe_version_id is not None
                        and existing["recipe_version_id"] != recipe_version_id)):
                raise ValueError("Requested copy identity is already owned by another document")
            return existing  # An explicit operation identity may be retried safely.
    if parent.get("trashed", False):
        raise ValueError("Restore a trashed document before creating a virtual copy")
    row = copy.deepcopy(parent)
    row["document_id"] = new_document_id or str(uuid.uuid4())
    row["recipe_version_id"] = recipe_version_id or str(uuid.uuid4())
    row["copy_number"] = 1 + max(r["copy_number"] for r in project["docs"]
                                if r["root_document_id"] == parent["root_document_id"])
    if row["copy_number"] > 9007199254740991: raise ValueError("Copy numbering exceeds protocol integer range")
    row["document_revision"] = 0
    from .canvas_guides import copy_record
    row['canvas_guides'] = copy_record(parent.get('canvas_guides'))
    row.pop("_lrt_runtime_version", None)
    row["trashed"] = False
    if "document_history" in row:
        row["document_history"] = {"undo": [], "redo": []}
    for key in ("undo_history", "redo_history", "undo", "redo"):
        if key in row:
            row[key] = []
    candidate = {**project, "docs": [*project["docs"], row]}
    validate_identity(candidate)
    project["docs"].append(row)
    return row


def set_trashed(project, document_id, on):
    """Soft-delete roots with children; restoring a copy restores only its root.

    Restoring a root alone leaves siblings in trash. Repeating an operation is
    idempotent and returns no changes; recipes and source bytes remain untouched.
    """
    row = next((r for r in project["docs"] if r.get("document_id") == document_id), None)
    if row is None:
        raise ValueError(f"Unknown document: {document_id}")
    root_id, wanted = row["root_document_id"], bool(on)
    targets = [row]
    if wanted and document_id == root_id:
        targets = [r for r in project["docs"] if r["root_document_id"] == root_id]
    elif not wanted and document_id != root_id:
        root = next((r for r in project["docs"] if r["document_id"] == root_id), None)
        if root is None:
            raise ValueError("Cannot restore a copy whose root is missing")
        targets = [root, row]
    changed = []
    for target in targets:
        if bool(target.get("trashed", False)) != wanted:
            target["trashed"] = wanted
            changed.append(target["document_id"])
    return changed
