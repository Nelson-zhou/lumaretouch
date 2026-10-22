"""Bounded, frozen one-document preset reviews; no mutations or raster storage."""
from collections import OrderedDict
from copy import deepcopy
import time
import uuid
from . import scope as SC, local_grade_layers as LG, local_grade_runtime as LR
from .batch_preflight import canonical


class PresetReviews:
    def __init__(self): self.pending = OrderedDict()

    def prepare(self, preset, state, row, document_id, revision, options):
        modules = preset['modules']
        if LG.OP not in modules: raise ValueError('此预设不含独立局部调色，无需局部蒙版预检')
        prepared, transfer = LR.prepare_modules(state, modules, row, options, preview=True)
        token = uuid.uuid4().hex
        record = {'preset': deepcopy(preset), 'modules': prepared, 'transfer': transfer,
                  'document_id': document_id, 'revision': str(revision), 'path': row['path'],
                  'before': canonical(SC.params_of(state, list(modules))), 'local_key': LG.undo_key(state),
                  'expires': time.monotonic() + 30 * 60}
        canonical(record)
        self.pending[token] = record
        while len(self.pending) > 8: self.pending.popitem(last=False)
        return {'id': preset['id'], 'name': preset['name'], 'module_scope': list(modules),
                'preflight_token': token, 'applies': deepcopy(prepared), 'local_mask_transfer': transfer,
                'document_id': document_id, 'revision': str(revision)}

    def claim(self, token, preset_id, state, row, document_id, revision):
        if type(token) is not str or token not in self.pending: raise ValueError('局部预设预检已失效或使用，请重新预检')
        record = self.pending[token]
        if time.monotonic() >= record['expires']: raise ValueError('局部预设预检已过期，请重新预检')
        if (record['preset']['id'] != preset_id or record['document_id'] != document_id
                or record['path'] != row['path'] or record['revision'] != str(revision)):
            raise ValueError('照片、版本或预设与预检不同，请重新预检')
        if canonical(SC.params_of(state, list(record['modules']))) != record['before'] or LG.undo_key(state) != record['local_key']:
            raise ValueError('照片在预检后发生修改，请重新预检')
        LR.verify_modules(record['modules'], {**row, 'state':state}, record['transfer'])
        del self.pending[token]
        return record
