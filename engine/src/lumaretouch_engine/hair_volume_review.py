# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only source diagnostics and exact full mixed review. AUTHORED / UNRUN.

The unchanged full candidate renderer owns all numerical work and resampling.
Diagnostics draw observed vectors on actual source pixels, not a fake result.
"""
from copy import deepcopy
import base64
import hashlib
import io
import uuid
import numpy as np
from . import hair_volume_support as A, hair_volume_state as S
from . import creative_derived_source as SOURCE
from .portrait_review_render import snapshot_key, image as render_image, preview_size

MAX_PNG_BYTES = 4 * 1024 * 1024


def encode(image):
    if min(image.size) < 2 or max(image.size) > 1024:
        raise ValueError('Hair-volume review needs a bounded nondegenerate complete image')
    stream = io.BytesIO(); image.save(stream, format='PNG'); raw = stream.getvalue()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Hair-volume PNG exceeds bounded review transport')
    return {'png': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii'),
            'sha256': hashlib.sha256(raw).hexdigest(), 'width': image.width, 'height': image.height}


def source_pixels(engine, source):
    SOURCE.verify(source, engine)
    SOURCE.verify_precompute(engine, engine._precompute)
    rgb = SOURCE.analysis_rgb(engine)
    if (type(rgb) is not np.ndarray or rgb.dtype != np.uint8 or rgb.ndim != 3
            or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 2):
        raise ValueError('Actual source-view RGB pixels are unavailable; no fabricated contour canvas')
    return rgb


def source_image(engine, source):
    from PIL import Image
    with Image.fromarray(source_pixels(engine, source), 'RGB') as image:
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        return encode(image)


def staged_context(engine, row, candidate, bank):
    from .full_candidate_render import people_context
    staged = people_context(engine, row)
    old = staged['people_support_assets']
    if any(bank.get(key) != value for key, value in old.items()):
        raise ValueError('Hair-volume candidate cannot replace the shared immutable support bank')
    staged['people_graph'] = deepcopy(candidate)
    staged['people_support_assets'] = A.check_store(bank)
    return staged


def diagnostic(engine, state, record, output_size):
    """Whole SOURCE, letterboxed when final crop/rotation has another aspect.

    Cyan/yellow/magenta are measured crown/left/right boundaries. Green/red are
    actual hair/background probes. Orange boxes protect visible anatomy/people.
    This is neither the rendered candidate nor an instance-segmentation claim.
    """
    from PIL import Image, ImageDraw, ImageOps
    size = preview_size(output_size)
    if min(size) < 2:
        raise ValueError('The final crop is too narrow to review complete hair-volume images')
    with Image.fromarray(source_pixels(engine, record['source']), 'RGB') as original:
        with ImageOps.contain(original, size, Image.Resampling.LANCZOS) as source:
            width, height = source.size; draw = ImageDraw.Draw(source)
            def point(value):
                return value[0] * (width - 1), value[1] * (height - 1)
            def rectangle(value, colour, line=2):
                draw.rectangle((*point(value[:2]), *point(value[2:])), outline=colour, width=line)
            for region, colour in (('crown', '#00e5ef'), ('left', '#ffe13b'), ('right', '#ee6cff')):
                part = record['row']['regions'][region]
                if part is None:
                    continue
                x, y = part['x'], part['y']
                rectangle([x[0], y[0], x[3], y[3]], colour, 1)
                rectangle([x[1], y[1], x[2], y[2]], colour, 2)
                draw.line([point(value) for value in part['contour']], fill=colour, width=3)
                for name, sample_colour in (('hair_samples', '#50ff60'), ('background_samples', '#ff4848')):
                    for value in part[name]:
                        px, py = point(value)
                        draw.ellipse((px-2, py-2, px+2, py+2), fill=sample_colour)
            for face in state['faces'].values():
                if face['asset_sha256'] == record['source']['sha256']:
                    rectangle(face['box'], '#ffae35')
            for name in ('ears', 'neck', 'other_people'):
                for value in record['row']['protection'][name]:
                    rectangle(value, '#ffae35')
            with Image.new('RGB', size, '#20242b') as canvas:
                canvas.paste(source, ((size[0]-width)//2, (size[1]-height)//2))
                return encode(canvas)


def complete(engine, row, current, state, candidate, bank, captured, reference, record, recipe, consent):
    staged = staged_context(engine, row, candidate, bank)
    before_key = reference['before_key']
    after_key = snapshot_key(engine, row, current, candidate, staged_people_context=staged)
    before, before_image, proof_before = render_image(engine, row, current, state,
        captured['document_id'], captured['document_revision'])
    after, after_image, proof_after = render_image(engine, row, current, candidate,
        captured['document_id'], captured['document_revision'], staged_people_context=staged)
    source = captured['source']
    if (proof_before['source_proof'] != captured['source_proof']
            or proof_after['source_proof'] != captured['source_proof']
            or proof_before['source_size'] != [source['width'], source['height']]
            or proof_after['source_size'] != proof_before['source_size']
            or proof_before['output_size'] != proof_after['output_size']
            or (before['width'], before['height']) != (after['width'], after['height'])):
        raise ValueError('Complete mixed hair-volume review changed its exact source or output geometry')
    overlay = diagnostic(engine, state, record, proof_before['output_size'])
    if (overlay['width'], overlay['height']) != (before['width'], before['height']):
        raise ValueError('Complete hair-volume review and source diagnostic dimensions differ')
    token = uuid.uuid4().hex
    metadata = {'version': 1, 'operation_id': S.OPERATION_ID, 'preview_id': token,
        'source': source, 'source_proof': captured['source_proof'], 'face_ref': captured['face_ref'],
        'people_context': captured['people_context'], 'graph_fence': captured['graph_fence'],
        'recipe': recipe, 'support_asset_sha256': A.digest(record),
        'semantic_evidence_sha256': record['row']['semantic_evidence_sha256'],
        'region_confirmation': deepcopy(consent), 'source_image_sha256': reference['source_image_sha256'],
        'before_key': before_key, 'after_key': after_key, 'before_proof': proof_before, 'after_proof': proof_after,
        'before_sha256': before['sha256'], 'after_sha256': after['sha256'], 'support_sha256': overlay['sha256']}
    review_token = A.digest(metadata)
    payload = {'kind': 'preview', 'preview_id': token, 'review_token': review_token, 'preview_sha256': review_token,
        'source': deepcopy(source), 'face_ref': deepcopy(captured['face_ref']), 'recipe': deepcopy(recipe),
        'regions': deepcopy(record['row']['regions']), 'protection': deepcopy(record['row']['protection']),
        'support_asset_sha256': metadata['support_asset_sha256'],
        'semantic_evidence_sha256': metadata['semantic_evidence_sha256'],
        'before_png': 'data:image/png;base64,' + before_image['base64'],
        'after_png': 'data:image/png;base64,' + after_image['base64'], 'support_png': overlay['png'],
        'source_width': source['width'], 'source_height': source['height'],
        'support_domain': 'whole-source-letterboxed-not-final-crop'}
    for name, image in (('before', before), ('after', after), ('support', overlay)):
        payload.update({name + '_' + field: image[field] for field in ('sha256', 'width', 'height')})
    return payload, {'captured': deepcopy(captured), 'before': deepcopy(state), 'candidate': deepcopy(candidate),
        'bank': deepcopy(bank), 'staged': staged, 'before_key': before_key, 'after_key': after_key,
        'metadata': metadata, 'review_token': review_token, 'recipe': deepcopy(recipe), 'presented': None,
        'claimed': False}


def ack(entry, preview_id):
    return {'preview_id': preview_id, 'review_token': entry['review_token'],
            **{name: entry['metadata'][name] for name in ('before_sha256', 'after_sha256', 'support_sha256')}}


def image_bytes(value):
    if type(value) is str:
        return len(value) if value.startswith('data:image/') else 0
    if type(value) is dict:
        return sum(len(child) if name == 'base64' and type(child) is str else image_bytes(child)
                   for name, child in value.items())
    return sum(map(image_bytes, value)) if type(value) in (tuple, list) else 0


def bound_read_images(receipts, byte_limit):
    rows = [(key, image_bytes(record['result'])) for key, record in receipts.items()
            if 'result' in record and record['result'].get('action') in ('context', 'preview', 'status')]
    total = sum(size for _, size in rows)
    for key, size in rows:
        if total <= byte_limit:
            break
        if not size:
            continue
        old = receipts[key]
        result = {name: value for name, value in old['result'].items() if name not in ('payload', 'doc_state')}
        result.update(success=False, outcome_unknown=False, payload=None, payload_released=True,
            no_write=True, frame_emitted=False,
            error='Read-only hair-volume images released; request fresh context/preview with a new ID')
        receipts[key] = {**old, 'result': result}; total -= size
