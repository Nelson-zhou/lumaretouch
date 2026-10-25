# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen UNCROPPED current edited composite and new whole-frame face analysis.

Old original-proxy landmarks are never mapped across body/face/optics/manual
geometry. Fresh inference uses a hashed display proxy of the full edited raster,
not full-resolution inference. Only the private capture crop rect becomes full;
all non-crop effects and the real document remain unchanged. AUTHORED / UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256

from .portrait_crop_controller import canonical, digest
from .portrait_crop_review import display_rgb, encode_image, poll, raster_hash

MAX_WORK_BYTES = 2_000_000_000
MAX_ORIGINAL_BYTES = 512_000_000
MAX_FACES = 128
ROTATION_REASON = ('当前照片已有旋转。现有裁剪先裁后转，非零旋转下无法保证显示坐标的头顶留白和头部比例；'
                   '本模块暂不可用，不会清零旋转或丢弃其他编辑。')


def rotation_supported(state):
    value = state.get('_crop_rotation')
    # Do not use renderer's half-degree snap as permission to replace the recipe.
    return type(value) in (int, float) and value == 0


def file_hash(path, *, cancelled=lambda: False):
    from .local_mask_state import file_stamp
    before = file_stamp(path)
    if not 0 < before[2] <= MAX_ORIGINAL_BYTES:
        raise ValueError('Portrait crop original provenance exceeds the source budget')
    result = sha256()
    total = 0
    with open(path, 'rb') as stream:
        while True:
            poll(cancelled)
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_ORIGINAL_BYTES:
                raise ValueError('Portrait crop original grew beyond its bounded provenance budget')
            result.update(block)
    if file_stamp(path) != before:
        raise ValueError('Portrait crop original changed while hashing its content')
    return result.hexdigest()


def hot_fence(engine):
    from .expression_replacement_source import hot_fence as current
    return current(engine)


def _analysis(proxy, source_size, *, cancelled=lambda: False):
    """Model-derived proposals only. In particular no detected crown exists."""
    import numpy as np
    from . import face as F
    from .people_binding import landmark_digest
    w, h = source_size
    poll(cancelled)
    with F.build('mediapipe') as backend:
        pc = backend(proxy)
        poll(cancelled)
    if (pc.backend != 'mediapipe' or pc.manual or pc.detection_limit_reached
            or not 1 <= pc.num_faces <= MAX_FACES or len(pc.all_landmarks) != pc.num_faces
            or not digest(pc.detector_model_sha256) or not digest(pc.semantic_model_sha256)):
        raise ValueError('Portrait crop needs complete genuine fresh face evidence on this edited image')
    faces = []
    seen = set()
    for points in pc.all_landmarks:
        poll(cancelled)
        lm_sha = landmark_digest(points)
        if lm_sha in seen:
            raise ValueError('Fresh portrait crop detector has ambiguous duplicate face evidence')
        seen.add(lm_sha)
        xy = np.asarray(points)[:, :2]
        low, high = np.clip(xy.min(0), 0, 1), np.clip(xy.max(0), 0, 1)
        if np.any(low >= high):
            raise ValueError('Fresh portrait crop detector has a degenerate face box')
        chin = [float(points[152][0]) * w, float(points[152][1]) * h]
        if not 0 <= chin[0] <= w or not 0 <= chin[1] <= h:
            raise ValueError('The detected chin is outside this complete source; manual inspection required')
        box = [float(low[0]) * w, float(low[1]) * h, float(high[0]) * w, float(high[1]) * h]
        faces.append({'face_id': 'face:' + lm_sha, 'landmarks_sha256': lm_sha, 'bbox': box,
                      'chin_proposal': chin,
                      'center_proposal': [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]})
    faces.sort(key=lambda value: value['face_id'])
    proxy_sha = sha256(memoryview(proxy).cast('B')).hexdigest()
    evidence = {'version': 1, 'source_size': source_size, 'proxy_size': [int(proxy.shape[1]), int(proxy.shape[0])],
                'proxy_sha256': proxy_sha, 'model_sha256': pc.detector_model_sha256,
                'semantic_model_sha256': pc.semantic_model_sha256, 'faces': faces,
                'mapping': 'source_edge_pixels', 'inference': 'fresh_whole_frame_display_proxy'}
    return {**evidence, 'analysis_sha256': sha256(canonical(evidence)).hexdigest()}


@dataclass(frozen=True)
class Capture:
    row: object
    state: dict
    binding: dict
    source: dict
    before: dict
    before_proof: dict
    uncropped_proof: dict
    capture_sha256: str
    hot: object
    retained_bytes: int
    max_bytes: int

    def stale(self, engine):
        try:
            return hot_fence(engine) != self.hot
        except (ValueError, OSError, KeyError, IndexError, AttributeError):
            return True

    def verify(self, engine, *, cancelled=lambda: False):
        from .full_candidate_render import identity
        from .optics_candidate_identity import fingerprint
        stopped = lambda: cancelled() or self.stale(engine)
        poll(stopped)
        current = engine._capture_state()
        if fingerprint(current) != self.binding['state_sha256']:
            raise ValueError('Portrait crop source edits or repair history changed after capture')
        actual, _, _ = identity(engine, self.row, self.state, self.binding['document_id'], self.binding['revision'])
        for key in ('source_proof', 'people_sha256'):
            if actual[key] != self.binding[key]:
                raise ValueError('Portrait crop source, portrait graph or retained analysis changed')
        if file_hash(self.row['path'], cancelled=stopped) != self.binding['original_sha256']:
            raise ValueError('Portrait crop original content changed after the full-image review')
        poll(stopped)


def capture_current(engine, *, max_bytes=MAX_WORK_BYTES, cancelled=lambda: False):
    from .full_candidate_render import identity, render
    from .optics_candidate_identity import fingerprint
    from .portrait_crop_project import non_crop_hash, repair_hash
    from .render_snapshot import own_render_inputs
    from .creative_edited_capture_admission import inspect_storage
    from .local_mask_state import file_stamp
    from .portrait_crop_review import image
    if type(max_bytes) is not int or not 64_000_000 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Portrait crop capture requires an explicit bounded working budget')
    index = engine._doc_index
    if not 0 <= index < len(engine._docs):
        raise ValueError('Open a genuine current photograph before portrait crop review')
    row = engine._docs[index]
    version = engine._document_versions().version(row)
    hot = hot_fence(engine)
    stopped = lambda: cancelled() or hot_fence(engine) != hot
    poll(stopped)
    live = engine._capture_state()
    if not rotation_supported(live):
        raise ValueError(ROTATION_REASON)
    initial_sha = fingerprint(live)
    # Census before private copying; this is admission, not measured process RSS.
    census = inspect_storage(live)
    if census.total_bytes * 4 + 128_000_000 > max_bytes:
        raise MemoryError('Portrait crop retained edit snapshots exceed the bounded working budget')
    owned = own_render_inputs(live, max_asset_bytes=max_bytes // 4)
    state = owned.value
    original = file_hash(row['path'], cancelled=stopped)
    state_proof, _, _ = identity(engine, row, state, version.document_id, str(version.revision))
    if original != state_proof['source_proof']['original_sha256']:
        raise ValueError('Portrait crop full original content disagrees with its canonical source proof')
    # Shallow dictionary is intentional: private owned arrays are immutable and
    # downstream canonical renderer owns its required copies independently.
    uncropped = dict(state)
    uncropped['_crop_rect'] = (0., 0., 1., 1.)
    if non_crop_hash(uncropped) != non_crop_hash(state):
        raise ValueError('Uncropped capture changed an unrelated edit')
    source = state_proof['source_proof']['creative_source']
    extent = [source['width'], source['height']] if source else [row.get('src_w'), row.get('src_h')]
    if any(type(value) is not int or value < 1 for value in extent):
        raise ValueError('Portrait crop requires a known complete canonical destination grid')
    pixels = extent[0] * extent[1]
    proxy_pixels = min(pixels, 1400 * 1400)
    # Covers held snapshots, canonical full-render copies/planes, source display,
    # fresh proxy inference and bounded transport. Backend allocators still have
    # their existing limits; this is deliberately not a peak-RSS guarantee.
    if census.total_bytes * 4 + pixels * 96 + proxy_pixels * 192 + 128_000_000 > max_bytes:
        raise MemoryError('Portrait crop full edited-source capture exceeds its working-set admission')
    rgb, full_proof = render(engine, row, uncropped, version.document_id, str(version.revision), cancelled=stopped)
    if full_proof['source_size'] != extent or full_proof['output_size'] != extent:
        raise ValueError('Uncropped edited composite is not the exact full canonical destination grid')
    full_sha = raster_hash(rgb)
    proxy = display_rgb(rgb, cancelled=stopped)
    del rgb  # No duplicate full image stays resident during backend inference.
    shown = encode_image(proxy, extent, cancelled=stopped)
    full_proof = {**full_proof, 'raster_sha256': full_sha, 'image_sha256': shown['sha256']}
    analysis = _analysis(proxy, extent, cancelled=stopped)
    del proxy
    if tuple(state['_crop_rect']) == (0., 0., 1., 1.):
        before = deepcopy(shown)
        before_proof = {**state_proof, 'source_size': extent, 'output_size': extent,
                        'raster_sha256': full_sha, 'image_sha256': shown['sha256']}
    else:
        before, before_proof = image(engine, row, state, version.document_id, str(version.revision), cancelled=stopped)
    source = {'width': extent[0], 'height': extent[1], 'orientation': 'exif_normalized_once',
              'mapping': 'source_edge_pixels', 'source_sha256': full_sha,
              'analysis_sha256': analysis['analysis_sha256'], 'model_sha256': analysis['model_sha256'],
              'semantic_model_sha256': analysis['semantic_model_sha256'], 'proxy_sha256': analysis['proxy_sha256'],
              'proxy_size': analysis['proxy_size'], 'inference': analysis['inference'],
              'image': shown, 'faces': analysis['faces']}
    binding = {'document_id': version.document_id, 'revision': str(version.revision),
               'document_epoch': engine._document_versions().workspace, 'load_id': engine._load_id,
               'original_sha256': original, 'source_proof': state_proof['source_proof'],
               'state_sha256': initial_sha, 'non_crop_sha256': non_crop_hash(state),
               'people_sha256': state_proof['people_sha256'], 'repair_sha256': repair_hash(state),
               'uncropped_sha256': full_sha}
    capture_sha = fingerprint({'version': 1, 'binding': binding,
                               'source': {key: value for key, value in source.items() if key != 'image'},
                               'source_image_sha256': shown['sha256'], 'before': before_proof})
    result = Capture(row, state, binding, source, before, before_proof, full_proof,
                     capture_sha, hot, census.total_bytes, max_bytes)
    result.verify(engine, cancelled=stopped)
    if file_stamp(row['path']) != hot[-1]:
        raise ValueError('Portrait crop provenance changed before source publication')
    return result
