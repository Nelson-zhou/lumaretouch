"""Source identity guards shared by retained-grade snapshots and full decode.

These helpers do not change editor state. Snapshot writes are limited to the
ephemeral source path and decode identity stamp, never a persisted proxy raster.
"""
from . import local_grade_layers as L
from . import local_mask_state as M


def has_groups(snap):
    return bool(L.check(snap.get('local_grade_groups'))['layers'])


def verify_snapshot(snap, path, shape=None):
    groups = L.check(snap.get('local_grade_groups'))
    if not groups['layers']:
        return
    before = M.file_stamp(path)
    if shape is not None:
        L.validate_budget(groups, shape)
    for layer in groups['layers']:
        M.verify_source(layer['mask'], path, shape)
    if M.file_stamp(path) != before:
        raise ValueError('Independent grade source changed while verifying its snapshot')


def check_export_decode(snap, path, before, shape):
    if not has_groups(snap):
        return
    if before is None or M.file_stamp(path) != before:
        raise ValueError('Independent grade source changed during full-resolution decoding')
    verify_snapshot(snap, path, shape)
    if M.file_stamp(path) != before:
        raise ValueError('Independent grade source changed after full-resolution decoding')
    snap['local_mask_source_path'] = path
    snap['local_grade_source_stamp'] = list(before)
