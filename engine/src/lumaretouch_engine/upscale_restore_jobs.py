# SPDX-License-Identifier: GPL-3.0-or-later
"""Reuse bounded reader cancellation coordination; never interrupt entered writes."""
import hashlib
from .light_glow_jobs import Jobs as SharedJobs
from .lens_blur_jobs import canonical, token


def command_hash(request):
    raw = canonical(request)
    if len(raw) > 16 * 1024:
        raise ValueError('Restoration command exceeds bounded wire budget')
    return hashlib.sha256(b'lrt-upscale-restore-host-command-v1\0' + raw).hexdigest()


class Jobs(SharedJobs):
    command_name = 'upscale_restore'
    operation_id = 'lnx.upscale_restore.v1'
    command_hash = staticmethod(command_hash)


def controller(engine):
    return engine.__dict__.setdefault('_upscale_restore_source_jobs', Jobs())
