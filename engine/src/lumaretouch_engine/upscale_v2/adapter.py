"""Bounded optional CPU adapter; source authored, runtime/photo acceptance UNRUN.

Status never downloads or imports Torch. Installation evidence remains an explicit
source gate. No identity, sharpening or resampling fallback is returned as AI.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Callable

from .architecture import CONTRACT_VERSION, architecture_for
from .source import CanonicalSource, validate_source

_JOB_LOCK = threading.Lock()


@dataclass(frozen=True)
class BackendCapability:
    model_id: str
    contract: str
    available: bool
    state: str
    blockers: tuple[str, ...]
    network_scale: int
    output_mode: str = 'restore_native_dimensions'
    installation_verified: bool = False
    inference_run: bool = False


@dataclass(frozen=True)
class NativeCandidate:
    rgba_f32le: bytes
    source_sha256: str
    result_sha256: str
    width: int
    height: int
    model_id: str
    network_scale: int
    raw_generated_statistics: dict
    native_resample_statistics: dict
    status: str = 'review_required'
    quality_acceptance: str = 'UNRUN'
    performance_acceptance: str = 'UNRUN'


class BackendUnavailable(RuntimeError):
    def __init__(self, status: BackendCapability):
        self.status = status
        super().__init__('AI clarity backend unavailable: ' + '; '.join(status.blockers))


def setup_status(*, root=None):
    from .setup import model_status
    return model_status(root)


def capability(model_id: str = 'Swin2SR-classical-sr-x2-64', *, root=None) -> BackendCapability:
    if model_id != 'Swin2SR-classical-sr-x2-64':
        return BackendCapability(model_id, CONTRACT_VERSION, False, 'unsupported_profile',
                                 ('Selected profile unavailable; RealESRGAN checkpoint license remains unresolved',), 2)
    status = setup_status(root=root)
    blockers = tuple(status.get('blockers', []))
    if not status['ready'] and not blockers:
        blockers = (status['reason'],)
    return BackendCapability(model_id, CONTRACT_VERSION, status['ready'], status['state'],
                             blockers, 2, installation_verified=status['installed'])


def restore_native_candidate(*, source: CanonicalSource, check_cancelled: Callable[[], None],
                             model_id: str = 'Swin2SR-classical-sr-x2-64', root=None) -> NativeCandidate:
    from . import setup as S
    from ..prompted_model_install import _run
    from ..cpu_memory_budget import available_estimate
    status = capability(model_id, root=root)
    if not status.available:
        raise BackendUnavailable(status)
    if (type(source) is not CanonicalSource or source.width < 16 or source.height < 16
            or source.width > S.MAX_SIDE or source.height > S.MAX_SIDE
            or source.width*source.height > S.MAX_PIXELS):
        raise ValueError('Source outside 16..1024px each-side full-frame CPU profile; no proxy, crop or resize fallback')
    validate_source(source, check_cancelled=check_cancelled)
    if available_estimate() < 4*1024**3 + len(source.rgba_f32le)*3:
        raise ValueError('Insufficient visible memory for bounded CPU worker and retained canonical source')
    if not _JOB_LOCK.acquire(blocking=False):
        raise ValueError('An AI clarity CPU job is already active')
    try:
        identity = S.runtime_identity(root)
        base = S.root_path(root)
        # Parent owns all temporary data; no result is exposed on crash/cancel.
        with tempfile.TemporaryDirectory(prefix='lrt-upscale-') as directory:
            path = Path(directory)
            import shutil
            if shutil.disk_usage(path).free < len(source.rgba_f32le)*2 + 64*1024**2:
                raise ValueError('Insufficient staging disk space for source and result')
            check_cancelled()
            with (path/'source.f32').open('xb') as stream:
                stream.write(source.rgba_f32le)
            (path/'request.json').write_text(json.dumps({'width': source.width, 'height': source.height,
                                                       'source_sha256': source.sha256}))
            def cancelled():
                check_cancelled()
                return False
            import sys
            _run([sys.executable, '-B', '-m', 'lumaretouch_engine.upscale_v2.worker', '--root', str(base),
                  '--output', str(path/'result.json'), '--request', str(path), '--parent-pid', str(os.getpid())],
                 cancelled, path/'worker.log', timeout=S.WALL_SECONDS)
            check_cancelled()
            meta = json.loads(S._read(path/'result.json', 65536))
            pixels = S._read(path/'result.f32', S.MAX_PIXELS*16)
            if (S.runtime_identity(root) != identity or meta.get('runtime') != identity
                    or meta.get('source_sha256') != source.sha256 or meta.get('width') != source.width
                    or meta.get('height') != source.height or meta.get('model_id') != model_id
                    or meta.get('network_scale') != 2 or meta.get('status') != 'review_required'):
                raise ValueError('Upscale result ownership or runtime identity mismatch')
            result_source = CanonicalSource(source.width, source.height, pixels, meta['result_sha256'])
            validate_source(result_source, check_cancelled=check_cancelled)
            check_cancelled()
            return NativeCandidate(pixels, source.sha256, hashlib.sha256(pixels).hexdigest(), source.width,
                                   source.height, model_id, 2, meta['raw_generated_statistics'],
                                   meta['native_resample_statistics'])
    finally:
        _JOB_LOCK.release()
