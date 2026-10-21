"""Bounded binary transport to the repository-owned Rust colour-scopes worker."""
from pathlib import Path
import json
import struct
import subprocess
import numpy as np
from .color_scopes_sampling import MAX_SAMPLES


def analyze(sample):
    pixels=sample.pixels
    count=sample.grid_width*sample.grid_height
    if not 1<=count<=MAX_SAMPLES or pixels.shape!=(sample.grid_height,sample.grid_width,3):
        raise ValueError('invalid bounded colour samples')
    worker=Path(__file__).resolve().parent/'bin'/'color-scopes'
    if not worker.is_file():raise RuntimeError('matching Rust colour-scopes worker is not installed')
    packet=b'LCS1'+struct.pack('<I',count)+np.asarray(pixels,dtype='<f4').tobytes(order='C')
    run=subprocess.run([str(worker)],input=packet,capture_output=True,timeout=5,check=False)
    if run.returncode:raise RuntimeError('colour-scopes worker failed: '+run.stderr[:512].decode(errors='replace'))
    if len(run.stdout)>32768:raise ValueError('colour-scope response exceeds budget')
    result=json.loads(run.stdout)
    if result.get('version')!=1 or result.get('samples')!=count or result.get('bins')!=256:
        raise ValueError('colour-scope worker contract mismatch')
    return result
