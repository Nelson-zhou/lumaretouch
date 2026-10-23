"""Read-only, source-coordinate face choices for one reviewed parameter transfer.

No analysis, graph classification, selection, association or history mutation.
Images are bounded display-only views of each actual effective source, not edited
filmstrip thumbnails or an original image labelled as a derived composite.
"""
from copy import deepcopy
import base64
import hashlib
import io
import json

from . import people_state as S, virtual_copy_people as V, creative_derived_source as SOURCE

MAX_TARGETS = 16
MAX_FACES = 128
PREVIEW_EDGE = 320
MAX_RESULT_BYTES = 7 * 1024 * 1024
PROOF_FIELDS = {'document', 'people_scope', 'state_revision', 'association_revision',
                'graph_sha256', 'source_proof'}


def graph_digest(graph):
    graph = S.check(graph)
    raw = json.dumps(graph, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(b'lumaretouch-transfer-graph-v1\0' + raw).hexdigest()


def check_proof(value):
    if type(value) is not dict or set(value) != PROOF_FIELDS:
        raise ValueError('Transfer endpoint requires exact document, owner, source and graph proof')
    document = value['document']
    if type(document) is not dict or set(document) != {'document_id', 'epoch', 'revision'}:
        raise ValueError('Transfer endpoint requires an exact document fence')
    S.token(document['document_id']); S.token(document['epoch']); S.revision(document['revision'])
    S.token(value['people_scope'])
    if value['people_scope'] not in ('project', document['document_id']):
        raise ValueError('Transfer endpoint names another portrait owner')
    S.revision(value['state_revision']); S.revision(value['association_revision'])
    S.digest(value['graph_sha256']); SOURCE.check_row_proof(value['source_proof'])
    return deepcopy(value)


def proof(engine, row, graph, *, source_row=None):
    versions = engine._document_versions(); version = versions.version(row)
    return check_proof({'document': {'document_id': version.document_id,
                       'epoch': versions.workspace, 'revision': version.revision},
        'people_scope': V.scope(row), 'state_revision': graph['revision'],
        'association_revision': graph['association_revision'], 'graph_sha256': graph_digest(graph),
        'source_proof': SOURCE.row_proof(row if source_row is None else source_row)})


def verify(engine, row, graph, expected, *, source_row=None):
    expected = check_proof(expected)
    if proof(engine, row, graph, source_row=source_row) != expected:
        raise ValueError('Reviewed document, portrait owner, source or graph changed')
    return expected


def _source_row(engine, row):
    # The current row may not yet have remembered the latest returned baseline.
    # Read that one live field without capturing/saving or replacing its state.
    if row is V.current_row(engine):
        return {**row, 'state': {'_creative_base': getattr(engine, '_creative_base', None)}}
    return row


def _preview(row, expected, faces):
    from PIL import Image
    from .creative_document_base import from_state, proxy_for_state
    state = row.get('state') or {}
    base = from_state(state)
    if base is not None:
        # This existing bounded canonical-byte check refuses alpha/HDR before
        # the display-only converter could matte or clip them into a false proof.
        from .creative_document_host import require_photo_return
        require_photo_return(base)
        rgb = proxy_for_state(None, state, max_pixels=PREVIEW_EDGE * PREVIEW_EDGE)
        source_size = (base['width'], base['height'])
    else:
        from .decode import load_rgb
        decoded = load_rgb(row['path'], budget=PREVIEW_EDGE * PREVIEW_EDGE, device='cpu')
        rgb = decoded.rgb; source_size = (decoded.src_w, decoded.src_h)
    if any((face['evidence']['source_width'], face['evidence']['source_height']) != source_size for face in faces):
        raise ValueError('Retained face coordinates do not match this actual source extent')
    image = Image.fromarray(rgb)
    image.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
    width, height = image.size; out = io.BytesIO()
    image.save(out, format='PNG'); image.close()
    encoded = base64.b64encode(out.getvalue()).decode('ascii')
    if len(encoded) > 400_000:
        raise ValueError('Source face-choice preview exceeds its bounded transport budget')
    return {'mime': 'image/png', 'base64': encoded, 'width': width, 'height': height,
            'source_sha256': expected['source_proof']['asset_sha256']}


def entry(engine, row):
    graph = V.peek_graph(engine, row)
    if graph is None:
        raise ValueError('Open and analyse this independent photo before selecting a transfer face')
    source_row = _source_row(engine, row)
    expected = proof(engine, row, graph, source_row=source_row)
    asset = expected['source_proof']['asset_sha256']
    faces = [face for face in graph['faces'].values() if face['asset_sha256'] == asset]
    if not faces:
        raise ValueError('This effective source has no retained analysed face; open and analyse it first')
    if len(faces) > MAX_FACES:
        raise ValueError('Face-choice inventory exceeds its explicit review budget; no faces were omitted')
    preview = _preview(source_row, expected, faces)
    latest = V.peek_graph(engine, row)
    if latest is None:
        raise ValueError('Portrait owner became unavailable during face-choice preparation')
    verify(engine, row, latest, expected, source_row=_source_row(engine, row))
    return {**expected, 'faces': [{'face_ref': S.face_ref(face), 'box': list(face['box']),
              'enabled': face['enabled'], 'analysis_status': face['evidence']['status']}
              for face in sorted(faces, key=lambda face: face['face_instance_id'])],
            'source_preview': preview, 'blocked': None}


def inventory(engine, controller, request):
    if (type(request) is not dict or set(request) != {'cmd', 'action', 'request_id', 'docs'}
            or request['cmd'] != 'batch' or request['action'] != 'people_targets'):
        raise ValueError('Face inventory accepts only an exact read-only request')
    S.token(request['request_id'])
    docs = request['docs']
    if type(docs) is not list or not 1 <= len(docs) <= MAX_TARGETS or len(set(docs)) != len(docs):
        raise ValueError('Choose one to sixteen distinct target documents for visual face review')
    for identity in docs: S.token(identity)
    rows = engine._docs; current = V.current_row(engine)
    if current is None: raise ValueError('Open the source photograph first')
    source = entry(engine, current); targets = []; rejected = []
    for identity in docs:
        matches = [row for row in rows if row.get('document_id') == identity]
        if len(matches) != 1 or matches[0] is current:
            rejected.append({'doc': identity, 'error': 'Target document is missing, ambiguous or is the source'})
            continue
        row = matches[0]
        try:
            if row.get('trashed'): raise ValueError('Target photograph is in the project trash')
            targets.append(entry(engine, row))
        except Exception as error:
            # A blocked item has only routing identity, never a fabricated proof.
            targets.append({'document': {'document_id': identity}, 'blocked': str(error)[:2000]})
    verify(engine, current, V.peek_graph(engine, current),
           {key: source[key] for key in PROOF_FIELDS}, source_row=_source_row(engine, current))
    body = {'success': True, 'people_transfer': True, 'source': source,
            'targets': targets, 'rejected_docs': rejected}
    if len(json.dumps(body, separators=(',', ':'), allow_nan=False).encode()) > MAX_RESULT_BYTES:
        raise ValueError('Face-choice receipt exceeds its budget; select fewer target documents')
    controller.emit_result(request, body)
