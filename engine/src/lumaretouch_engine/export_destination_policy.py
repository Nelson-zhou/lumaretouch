"""M09 local destination planning. No rendering, mkdir or queue execution on preview.

Plans bind document/copy identity and frozen frame receipts, not source-path keys.
Filesystem inspection is advisory; export_destination_commit supplies no-clobber commit.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

SCHEMA = "lrt.export-destination.v1"

class DestinationError(ValueError):
    def __str__(self):
        code = super().__str__()
        labels = {
            'destination_missing_requires_creation_choice':'目标文件夹尚不存在，请勾选允许创建缺失文件夹后重新预览',
            'destination_read_only':'目标文件夹只读，请选择可写位置',
            'destination_not_searchable':'无法访问目标父目录，请检查权限',
            'unsafe_destination_ancestor':'目标目录包含符号链接或非目录项，请选择真实目录',
            'absolute_local_path_required':'请填写本机绝对路径',
            'invalid_path_component':'文件或文件夹名称无效，不能包含路径穿越字符',
            'missing_source_or_import_root':'原图已不存在，请先重新连接来源',
        }
        return labels.get(code,code) + (f' ({code})' if code in labels else '')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def component(value):
    if not isinstance(value, str) or not value or value in (".", "..") or any(c in value for c in ('/', '\\', '\0')):
        raise DestinationError("invalid_path_component")
    if len(os.fsencode(value)) > 255:
        raise DestinationError("filename_too_long")
    return value


def suffixed_name(stem, suffix, extension=''):
    budget = 255 - len(os.fsencode(suffix + extension))
    if budget < 1: raise DestinationError('filename_too_long')
    bounded = os.fsencode(stem)[:budget].decode('utf-8', 'ignore')
    return component(bounded + suffix + extension)


def absolute(value):
    if not isinstance(value, str) or not value.startswith('/') or '\0' in value or '\\' in value or '..' in value.split('/'):
        raise DestinationError("absolute_local_path_required")
    return Path(os.path.normpath(value))


def inspect_directory(path):
    """Reject symlink ancestors, non-directories and visibly read-only parents."""
    missing = []
    current = Path('/')
    nearest = current
    for name in path.parts[1:]:
        current /= name
        try:
            info = current.lstat()
        except FileNotFoundError:
            missing.append(str(current))
            continue
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise DestinationError("unsafe_destination_ancestor")
        if not os.access(current, os.X_OK):
            raise DestinationError("destination_not_searchable")
        nearest = current
    if not nearest.stat().st_mode & 0o222 or not os.access(nearest, os.W_OK | os.X_OK):
        raise DestinationError("destination_read_only")
    return tuple(missing)


@dataclass(frozen=True)
class Source:
    item_id: str
    source_path: str
    import_root: str
    frame_receipt: str
    target_filename: str
    import_relative: str | None = None
    output_subdirectory: str = ""
    destination_root: str | None = None
    origin_kind: str = "file"


@dataclass(frozen=True)
class Policy:
    mode: str = "chosen_root"
    chosen_root: str | None = None
    retain_hierarchy: bool = False
    source_subfolder: str = "project"
    project_name: str = "Exports"
    conflict: str = "rename"
    create_missing: bool = False
    layout_root: str | None = None


@dataclass(frozen=True)
class Entry:
    item_id: str
    source_path: str
    source_stamp: tuple[int, int, int, int]
    frame_receipt: str
    target: str
    disposition: str
    renamed_from: str | None
    missing_directories: tuple[str, ...]
    origin_kind: str = "file"


@dataclass(frozen=True)
class Plan:
    schema_version: str
    intent_revision: int
    settings_json: str
    policy_json: str
    entries: tuple[Entry, ...]
    plan_id: str

    def payload(self):
        return asdict(self)


def freeze(sources, policy, settings, intent_revision, *, protected_sources=()):
    """settings is the exact existing export options payload, copied without defaults.

    Caller supplies all project originals (not just selected items) as protected_sources.
    Source records come from the engine's frozen document list, never client paths alone.
    """
    if not isinstance(intent_revision, int) or isinstance(intent_revision, bool) or intent_revision < 0:
        raise DestinationError("invalid_intent_revision")
    if policy.mode not in ("chosen_root", "source_folder") or policy.source_subfolder not in ("none", "project", "import_root") or policy.conflict not in ("rename", "skip", "ask"):
        raise DestinationError("invalid_destination_policy")
    if type(policy.create_missing) is not bool or type(policy.retain_hierarchy) is not bool:
        raise DestinationError("invalid_destination_flags")
    if not sources or len(sources) > 100000:
        raise DestinationError("invalid_batch_size")
    if len({s.item_id for s in sources}) != len(sources):
        raise DestinationError("duplicate_item_identity")
    protected = {str(absolute(p).resolve(strict=False)) for p in protected_sources}
    protected.update(str(absolute(s.source_path).resolve(strict=True)) for s in sources)
    roots = sorted({str(absolute(s.import_root)) for s in sources})
    root_names = {}
    for root in roots:
        leaf = component(Path(root).name or "root")
        peers = [r for r in roots if Path(r).name.casefold() == leaf.casefold()]
        root_names[root] = leaf if len(peers) == 1 else suffixed_name(leaf, '-' + sha256(root.encode()).hexdigest()[:12])
    entries, reserved = [], set()
    # Stable ordering makes names independent of UI selection order.
    for source in sorted(sources, key=lambda s: s.item_id):
        if not source.item_id or not source.frame_receipt:
            raise DestinationError("missing_frozen_document_identity")
        src, root = absolute(source.source_path), absolute(source.import_root)
        try:
            relative = Path(source.import_relative) if source.import_relative is not None else src.relative_to(root)
            if relative.is_absolute(): raise ValueError()
            for part in relative.parts: component(part)
        except ValueError as exc:
            raise DestinationError("source_outside_import_root") from exc
        if not relative.parts or not src.is_file():
            raise DestinationError("missing_source_or_import_root")
        # Reject source aliases crossing outside the declared import tree.
        if source.import_relative is None and not src.resolve().is_relative_to(root.resolve()):
            raise DestinationError("source_symlink_escape")
        stamp = src.stat()
        filename = component(source.target_filename)
        if policy.mode == "chosen_root":
            destination = absolute(policy.chosen_root)
            if policy.retain_hierarchy:
                destination = destination / root_names[str(root)] / relative.parent
        else:
            destination = src.parent
            if policy.source_subfolder == "project":
                destination /= component(policy.project_name)
            elif policy.source_subfolder == "import_root":
                destination /= component(root.name or "root")
        if source.destination_root is not None:
            destination = absolute(source.destination_root)
        if source.output_subdirectory:
            if source.output_subdirectory.startswith("/"): raise DestinationError("invalid_variant_directory")
            for part in source.output_subdirectory.split("/"): component(part)
            destination /= source.output_subdirectory
        missing = inspect_directory(destination)
        if missing and not policy.create_missing:
            raise DestinationError("destination_missing_requires_creation_choice")
        target, original = destination / filename, None
        disposition = "write"
        def collision(candidate):
            return str(candidate).casefold() in reserved or os.path.lexists(candidate) or str(candidate.resolve()) in protected
        if collision(target):
            original = str(target)
            if policy.conflict == "rename":
                for n in range(1, 10000):
                    candidate = destination / suffixed_name(Path(filename).stem, f"-{n:04d}", Path(filename).suffix)
                    if not collision(candidate):
                        target = candidate
                        break
                else:
                    raise DestinationError("destination_names_exhausted")
            else:
                disposition = "skip" if policy.conflict == "skip" else "needs_confirmation"
        reserved.add(str(target).casefold())
        entries.append(Entry(source.item_id, str(src), (stamp.st_dev, stamp.st_ino, stamp.st_size, stamp.st_mtime_ns), source.frame_receipt, str(target), disposition, original, missing, source.origin_kind))
    body = dict(schema_version=SCHEMA, intent_revision=intent_revision,
                settings_json=canonical(settings), policy_json=canonical(asdict(policy)),
                entries=tuple(entries))
    return Plan(**body, plan_id=digest({**body, "entries": [asdict(e) for e in entries]}))


def restore(payload):
    """Persisted local queue payload: never recompute names on retry."""
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "intent_revision", "settings_json", "policy_json", "entries", "plan_id"} or payload.get("schema_version") != SCHEMA:
        raise DestinationError("invalid_destination_plan")
    entries = tuple(Entry(**{**e, "source_stamp": tuple(e["source_stamp"]), "missing_directories": tuple(e["missing_directories"])}) for e in payload["entries"])
    plan = Plan(**{**payload, "entries": entries})
    body = plan.payload(); body.pop("plan_id")
    if digest(body) != plan.plan_id:
        raise DestinationError("destination_plan_integrity")
    for entry in entries:
        absolute(entry.source_path); absolute(entry.target)
        if entry.disposition not in ("write", "skip", "needs_confirmation"):
            raise DestinationError("invalid_disposition")
    return plan
