# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable edited-photo capture and its own actual face analysis.

This producer never activates a photo, writes a graph, identifies a person, or
relabels the original image's analysis. Model execution is a runtime operation;
this authored source has not been executed or imported during development.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import numpy as np

PROTOCOL = 1
MAX_PROXY_PIXELS = 4_000_000
MAX_FACES = 128


@dataclass(frozen=True)
class Capture:
    asset: dict
    source: dict
    original_sha256: str
    graph: dict
    analyses: dict
    proxy: np.ndarray
    proxy_sha256: str
    detector_sha256: str
    semantic_sha256: str
    document_fence: dict | None


def current_fence(engine):
    """Actual canonical document and graph owners, not UI counters."""
    from .creative_document_host import token
    binding = engine._people_binding()
    graph = engine._people_owner().snapshot()
    from .people_source_context import digest
    return {**binding, 'load_id': engine._load_id, 'creative_owner': token(engine),
            'state_revision': graph['revision'],
            'association_revision': graph['association_revision'],
            'people_graph_sha256': digest(graph, binding['asset_sha256'])}


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Expression source acquisition cancelled before publication')


def require_opaque_sdr(asset, *, cancelled=lambda: False):
    """Check real linear coverage/range in bounded rows before display matting."""
    from .creative_document_assets import validate_asset
    asset = validate_asset(asset)
    if asset['kind'] != 'rgba':
        raise ValueError('Expression replacement requires a real RGBA source asset')
    rgba = np.frombuffer(asset['content'], dtype='<f4').reshape(asset['height'], asset['width'], 4)
    for start in range(0, asset['height'], 128):
        _poll(cancelled)
        block = rgba[start:start+128]
        if not np.isfinite(block).all() or np.any(block[:, :, 3] != 1):
            raise ValueError('Expression replacement does not flatten transparent source coverage')
        if np.any(block[:, :, :3] < 0) or np.any(block[:, :, :3] > 1):
            raise ValueError('Expression replacement does not clip HDR or signed source values')
    return asset


def analyse_asset(asset, original_sha256, *, document_fence=None,
                  max_bytes, cancelled=lambda: False):
    """Fresh MediaPipe on precisely this captured source's display proxy.

    The proxy is an explicit inference/display input only. Full-resolution linear
    pixels remain in the immutable asset for numerical alignment and blending.
    No original or another document's semantic masks enter the returned graph.
    """
    from . import face as F, people_state as P, people_binding as B
    from .creative_document_base import proxy_for_state
    from .creative_derived_source import binding
    from .creative_document_assets import MAX_STORE_BYTES
    P.digest(original_sha256)
    if type(max_bytes) is not int or not 16_777_216 <= max_bytes <= MAX_STORE_BYTES:
        raise ValueError('Expression acquisition requires an explicit bounded memory budget')
    asset = require_opaque_sdr(asset, cancelled=cancelled)
    pixels = min(MAX_PROXY_PIXELS, asset['width'] * asset['height'])
    # Model tensors have their own backend limits. Reserve source + the proxy,
    # semantic planes and retained analysis copies before asking that backend.
    if len(asset['content']) + pixels * 160 + 64_000_000 > max_bytes:
        raise ValueError('Expression source and genuine face-analysis working set exceed budget')
    _poll(cancelled)
    proxy = proxy_for_state(None, {'_creative_base': asset}, max_pixels=pixels, max_bytes=max_bytes)
    if proxy.dtype != np.uint8 or proxy.ndim != 3 or proxy.shape[2] != 3:
        raise ValueError('Expression inference proxy is not the actual RGB source projection')
    proxy = np.ascontiguousarray(proxy)
    proxy.setflags(write=False)
    sha = hashlib.sha256(memoryview(proxy).cast('B')).hexdigest()
    source = binding({'_creative_base': asset})
    with F.build('mediapipe') as backend:
        _poll(cancelled)
        pc = backend(proxy)
        _poll(cancelled)
    if (pc.backend != 'mediapipe' or pc.manual or pc.detection_limit_reached
            or not 1 <= pc.num_faces <= MAX_FACES
            or len(pc.all_landmarks) != pc.num_faces):
        raise ValueError('Expression replacement requires complete genuine automatic face evidence')
    P.digest(pc.detector_model_sha256)
    P.digest(pc.semantic_model_sha256)
    pc.input_source_binding = {**source, 'proxy_width': int(proxy.shape[1]),
                               'proxy_height': int(proxy.shape[0]), 'proxy_sha256': sha}
    graph, analyses, unresolved = B.bind(P.empty(), source['sha256'], pc,
        source_dimensions=(source['width'], source['height']), initialize=True)
    if unresolved or len(analyses) != pc.num_faces:
        raise ValueError('Expression source has ambiguous or incomplete retained face ownership')
    _poll(cancelled)
    return Capture(deepcopy(asset), source, original_sha256, graph, analyses,
                   proxy, sha, pc.detector_model_sha256, pc.semantic_model_sha256,
                   deepcopy(document_fence))


def capture_current(engine, *, max_bytes, cancelled=lambda: False):
    """Full current recipe first, then independently measured output anatomy.

    Crops, rotations, body/face geometry and repairs are baked by the existing
    complete export capture. Their original landmarks are never reused here.
    The current document itself remains unchanged until a later reviewed commit.
    """
    from .creative_document_base import capture_current_asset
    from .creative_document_assets import AssetStore
    staged_assets = AssetStore()
    before = current_fence(engine)
    from .creative_document_host import token
    from .local_mask_state import source_digest, file_stamp
    row = engine._docs[engine._doc_index]
    index = engine._doc_index
    versions = engine._document_versions()
    version = versions.version(row)
    graph_owner = engine._people_owner()
    graph_fence = graph_owner.fence
    stamp = file_stamp(row['path'])
    original = source_digest(row['path'])
    def stopped():
        # Hot native/model polls must not rehash source bytes or snapshot graphs.
        # Exact content proofs are rechecked only at operation boundaries below.
        return (cancelled() or engine._doc_index != index or engine._docs[index] is not row
                or engine._load_id != before['load_id'] or token(engine) != before['creative_owner']
                or engine._document_versions() is not versions or versions.version(row) != version
                or engine._people_owner() is not graph_owner or graph_owner.fence != graph_fence
                or file_stamp(row['path']) != stamp)
    _poll(stopped)
    state = engine._capture_state()
    asset = capture_current_asset(engine, row, state, staged_assets,
                                  max_bytes=max_bytes, cancelled=stopped)
    if source_digest(row['path']) != original:
        raise ValueError('Original provenance changed during edited-photo capture')
    result = analyse_asset(asset, original, document_fence=before,
                           max_bytes=max_bytes, cancelled=stopped)
    _poll(stopped)
    if current_fence(engine) != before:
        raise ValueError('Expression source proof changed before acquisition publication')
    return result


def capture_file(path, *, max_bytes, cancelled=lambda: False):
    """Explicit selected local donor file, never a URL or another live graph."""
    from .creative_document_import import import_file
    from .creative_document_assets import AssetStore
    staged_assets = AssetStore()
    from .local_mask_state import file_stamp, source_digest
    before = file_stamp(path)
    original = source_digest(path)
    identity = import_file(path, staged_assets, max_bytes=max_bytes, cancelled=cancelled)
    _poll(cancelled)
    if file_stamp(path) != before or source_digest(path) != original:
        raise ValueError('Donor file changed during immutable source acquisition')
    return analyse_asset(staged_assets.get(identity, 'rgba'), original,
                         max_bytes=max_bytes, cancelled=cancelled)


def resident_bytes(*values):
    """Count unique retained byte/array backing storage without decoding it."""
    from dataclasses import is_dataclass, fields
    seen=set()
    def size(value):
        if id(value) in seen:return 0
        seen.add(id(value))
        if isinstance(value, bytes):return len(value)
        if isinstance(value, np.ndarray):
            if value.base is not None:return size(value.base)
            return value.nbytes
        if isinstance(value, memoryview):return size(value.obj)
        if isinstance(value, dict):return sum(size(v) for v in value.values())
        if isinstance(value,(list,tuple)):return sum(size(v) for v in value)
        if is_dataclass(value):return sum(size(getattr(value,f.name)) for f in fields(value))
        return 0
    return sum(size(value) for value in values)


def hot_fence(engine):
    """Cheap owner/revision/file-stamp fence for frequent cancellation polls."""
    from .creative_document_host import token
    from .local_mask_state import file_stamp
    index=engine._doc_index
    if not 0 <= index < len(engine._docs):return None
    row=engine._docs[index]
    versions=engine._document_versions()
    owner=engine._people_owner()
    return (id(row),versions.workspace,versions.version(row),engine._load_id,
            token(engine),id(owner),owner.fence,file_stamp(row['path']))
