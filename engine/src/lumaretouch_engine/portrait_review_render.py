# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared full portrait review snapshot and display-only image primitives.

No controller, recipe, token, graph publication or history ownership lives here.
All runtime/numerical acceptance is UNRUN.
"""
from hashlib import sha256
import base64
import io

MAX_PNG_BYTES = 4 * 1024 * 1024
PREVIEW_EDGE = 1024


def preview_size(output):
    if type(output) is not list or len(output) != 2 or any(type(x) is not int or not 1 <= x <= 2**32-1 for x in output):
        raise ValueError('Review requires exact full output dimensions')
    edge=max(output)
    if edge<=PREVIEW_EDGE:return tuple(output)
    def extent(value):
        quotient,remainder=divmod(value*PREVIEW_EDGE,edge)
        return max(1,quotient+int(remainder*2>edge or (remainder*2==edge and quotient%2==1)))
    return tuple(extent(value) for value in output)


def _graph_content(graph):
    from .people_state import check
    value = check(graph)
    # Only graph commit counters are metadata. Every recipe/face/association
    # value remains in the comparison; no revision-dependent rebase is allowed.
    value['revision'] = 0
    return value


def snapshot_key(engine, row, state, graph):
    from .full_candidate_render import people_context
    from .people_export import isolated_snapshot
    from .optics_candidate_identity import fingerprint
    context = people_context(engine, row)
    document = engine._document_versions().version(row).document_id
    snap = engine._state_to_export_snap(state, device='cpu', scale=1, upscale_backend='lanczos3', sharpen=0.,
        source_path=row['path'], people_graph=graph, people_context=context, people_document_id=document)
    snap = isolated_snapshot(snap, for_document=True)
    if snap.get('people') is None: raise ValueError('Preset complete snapshot omitted retained portrait ownership')
    snap = dict(snap); snap['people'] = dict(snap['people'])
    snap['people']['state'] = _graph_content(snap['people']['state'])
    return {'render_sha256': fingerprint(snap),
            'context_sha256': fingerprint({key: value for key, value in context.items() if key != 'people_graph'}),
            'graph_sha256': fingerprint(_graph_content(graph))}


def image(engine, row, state, graph, document, revision, *, cancelled=lambda: False):
    from .full_candidate_render import render
    from PIL import Image
    import numpy as np
    rgb, proof = render(engine, row, state, document, str(revision), people_graph=graph, cancelled=cancelled)
    if cancelled(): raise InterruptedError('Portrait image review cancelled')
    size = preview_size(proof['output_size']); channels = []
    for channel in range(3):
        if cancelled(): raise InterruptedError('Portrait image review cancelled')
        with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    # Display reduction only. Full source/export/recipe data is never quantized.
    with Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0, 1)*255).astype(np.uint8), 'RGB') as display:
        output = io.BytesIO(); display.save(output, format='PNG'); raw = output.getvalue()
    if len(raw) > MAX_PNG_BYTES: raise ValueError('Preset image exceeds bounded review transport; no detail reduction')
    if cancelled(): raise InterruptedError('Portrait image review cancelled')
    compact = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}, proof
