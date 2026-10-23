"""Short-lived whole-source locator for two independent shadow brush roles.

Display PNGs are not retained masks, estimator pixels, or export inputs. Source
decoding shares the existing immutable full-precision transport; token ownership
and the two geometric snapshots are independent of the spill tool.
"""
from copy import deepcopy
import time
import uuid
from .spill_removal_paint_source import dimensions, source_pixels, _png

ACTION = 'id_original_shadow_paint_source'
DOMAIN = 'source-normalized'


def _mask_png(binding, source, width, height):
    import numpy as np
    from . import original_shadow_state as S
    value = (np.zeros((height, width), np.float32) if binding is None
             else S.raster(binding, (height, width), source=source))
    return _png(np.repeat(value[:, :, None], 3, axis=2), width, height)


class PaintSource:
    def __init__(self, engine):
        self.engine, self.record = engine, None

    def _proof(self, request):
        from .original_shadow_review import _context
        from .full_candidate_render import identity
        from . import creative_derived_source as D, local_mask_state as M
        row, document, revision = _context(self.engine, request)
        stamp = M.file_stamp(row['path'])
        source = D.binding(self.engine)
        proof, _, _ = identity(self.engine, row, self.engine._capture_state(), document, revision)
        D.verify(source, self.engine)
        if M.file_stamp(row['path']) != stamp:
            raise ValueError('原阴影画布准备期间源文件变化')
        return {'document_id': request['document_id'], 'recipe_document_id': document,
                'recipe_revision': revision, 'source': source,
                'identity': proof, 'original_stamp': stamp}

    def prepare(self, request):
        self.record = None
        from .original_shadow_controller import BASE
        if type(request) is not dict or set(request) != BASE or request['action'] != ACTION or request['cmd'] != 'background':
            raise ValueError('原阴影画布请求字段无效')
        from . import id_background_state as I, original_shadow_state as S
        proof = self._proof(request)
        width, height = dimensions(proof['source'])
        shadow = I.original_shadow_of(getattr(self.engine, '_id_background', None))
        bindings = {role: deepcopy(shadow[role]) for role in ('lit_floor', 'retention')}
        for binding in bindings.values():
            if binding is not None and S.check_binding(binding)['mask']['source'] != proof['source']:
                raise ValueError('原阴影画布范围属于另一张源图')
        pixels = source_pixels(self.engine, proof['source'])
        image = _png(pixels, width, height)
        del pixels
        masks = {role: _mask_png(binding, proof['source'], width, height)
                 for role, binding in bindings.items()}
        if self._proof(request) != proof:
            raise ValueError('原阴影源图、配方或人物归属在画布准备期间变化')
        self.record = {**deepcopy(proof), 'token': uuid.uuid4().hex,
                       'bindings': bindings, 'expires': time.monotonic() + 300.}
        return {'version': 1, 'token': self.record['token'],
                'recipe_document_id': proof['recipe_document_id'], 'recipe_revision': proof['recipe_revision'],
                'source': deepcopy(proof['source']), 'domain': DOMAIN, 'image': image, **masks}

    def _verify(self, request, token):
        record = self.record
        if (record is None or type(token) is not str or record['token'] != token
                or time.monotonic() > record['expires']):
            raise ValueError('原阴影源图画布已过期，请重新读取')
        expected = {key: record[key] for key in ('document_id', 'recipe_document_id',
                    'recipe_revision', 'source', 'identity', 'original_stamp')}
        if self._proof(request) != expected:
            self.record = None
            raise ValueError('原阴影笔画不属于当前画布的源图、配方或人物归属')
        return record

    def bindings(self, request, paint):
        if type(paint) is not dict or set(paint) != {'token', 'lit_strokes', 'retention_strokes'}:
            raise ValueError('原阴影画笔需要画布票据和两组笔画')
        groups = {'lit_floor': paint['lit_strokes'], 'retention': paint['retention_strokes']}
        if any(type(strokes) is not list for strokes in groups.values()) or not any(groups.values()):
            raise ValueError('原阴影画笔至少需要一条源图笔画')
        from .original_shadow_paint_vectors import append
        record = self._verify(request, paint['token'])
        result = {role: (append(record['bindings'][role], record['source'], strokes, role)
                         if strokes else deepcopy(record['bindings'][role]))
                  for role, strokes in groups.items()}
        if self._verify(request, paint['token']) is not record:
            raise ValueError('原阴影画布在准备笔画期间被替换')
        return result


def owner(engine):
    value = engine.__dict__.get('_original_shadow_paint_source_owner')
    if value is None:
        value = engine._original_shadow_paint_source_owner = PaintSource(engine)
    return value
