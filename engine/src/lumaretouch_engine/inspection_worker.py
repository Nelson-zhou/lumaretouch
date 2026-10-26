"""Standalone Linux CPU inspection worker. Resource limits precede heavy imports."""
import argparse
import json
import os
import resource
import stat


def bind_parent(expected_pid):
    """Do not leave the worker running if its Engine parent dies unexpectedly."""
    import ctypes as C
    import signal
    if type(expected_pid) is not int or expected_pid <= 1:
        raise ValueError('Invalid inspection parent identity')
    libc = C.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [C.c_int, C.c_ulong, C.c_ulong, C.c_ulong, C.c_ulong]
    prctl.restype = C.c_int
    if prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(C.get_errno(), 'Cannot bind inspection worker to parent')
    # Parent may have died between spawn and prctl; that earlier death would not
    # generate the newly configured signal. Fail closed on reparenting.
    if os.getppid() != expected_pid:
        raise RuntimeError('Inspection Engine parent already exited')


def source_identity(path):
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Inspection source must be a regular file')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def limits(address_bytes, output_bytes, cpu_seconds):
    # RLIMIT_AS is address space, NOT an RSS or total machine RAM guarantee.
    for value, low, high in ((address_bytes, 512*1024**2, 8*1024**3),
                              (output_bytes, 128, 64*1024**2+128),
                              (cpu_seconds, 1, 120)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Invalid worker resource limit')
    for key, requested in ((resource.RLIMIT_AS, address_bytes),
                           (resource.RLIMIT_FSIZE, output_bytes),
                           (resource.RLIMIT_CPU, cpu_seconds)):
        _, hard = resource.getrlimit(key)
        bound = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
        resource.setrlimit(key, (bound, bound))
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        os.environ[key] = '1'


def _decode_original(path, max_source_pixels):
    """Select native precision before decoding; never inspect RGB16 through RGB8."""
    from .decode import load_full, is_raw
    from .full_source_working import source_bits, require_opaque_8bit
    from PIL import Image
    if is_raw(path):
        bits = 16
    else:
        with Image.open(path) as image:
            if image.width * image.height > max_source_pixels:
                raise ValueError('Inspection source exceeds its admitted pixel budget')
            bits = 16 if source_bits(path, image) > 8 else 8
            if bits == 8:
                require_opaque_8bit(image)
    decoded = load_full(path, max_px=max_source_pixels, device='cpu', want_bits=bits)
    if bits == 16 and str(decoded.rgb.dtype) != 'uint16':
        raise ValueError('Full-source inspection requires genuine RGB16 decoding')
    # Leave uint16 in its source encoding. render_inspection_roi delegates its
    # single ICC conversion to render_edited_rgb16, just like edited export.
    return decoded


def render(directory):
    # All dependencies below are deliberately imported only after limits().
    from .inspection_bundle import read_bundle, _open_regular
    from .export_recipe import build_export_spec
    from .full_quality import render_inspection_roi
    from .inspection_job import validate_config
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    f, size = _open_regular(directory, 'request.json', 65536)
    with f:
        raw = f.read(65537)
    if len(raw) != size:
        raise ValueError('Inspection request changed')
    request = json.loads(raw)
    expected = {'path', 'source_identity', 'source_asset_id', 'epoch', 'ticket', 'roi', 'source_size',
                'canvas_size', 'max_source_pixels', 'max_display_pixels', 'max_asset_bytes',
                'max_address_bytes', 'timeout_seconds'}
    if type(request) is not dict or set(request) != expected:
        raise ValueError('Unknown inspection request')
    validate_config({k:v for k,v in request.items() if k not in ('path','source_identity','source_asset_id','max_asset_bytes')})
    path = request['path']
    if type(path) is not str or not path or len(path) > 32768:
        raise ValueError('Invalid inspection source path')
    before = source_identity(path)
    if before != request['source_identity']:
        raise ValueError('Inspection source changed before decode')
    snap = read_bundle(directory, max_asset_bytes=request['max_asset_bytes'])
    from .creative_document_base import from_state, require_rebound_snapshot
    base = from_state(snap)
    if request['source_asset_id'] != (base['id'] if base is not None else None):
        raise ValueError('Inspection canonical source identity mismatch')
    from .people_export import verify_source as verify_people, isolated_snapshot
    verify_people(snap,path);snap=isolated_snapshot(snap,for_document=True)
    if base is not None:
        # Original path remains provenance only. Never decode or borrow its
        # observations/pixels for this independently hashed baked source.
        if [base['width'], base['height']] != request['source_size']:
            raise ValueError('Creative inspection dimensions differ from admission')
        require_rebound_snapshot(snap)
        spec, skipped = build_export_spec(snap, base['height'], base['width'], for_document=True)
        pixels = render_inspection_roi(None, spec, request['roi'],
            max_source_pixels=request['max_source_pixels'], max_display_pixels=request['max_display_pixels'],
            device='cpu', crop_rect=tuple(snap.get('crop_rect', (0,0,1,1))),
            rotation_degrees=float(snap.get('crop_rotation', 0)), skipped_layers=skipped)
        if [pixels.canvas_width, pixels.canvas_height] != request['canvas_size']:
            raise ValueError('Rendered creative canvas differs from admission')
        if source_identity(path) != before:
            raise ValueError('Original provenance changed during creative inspection')
        _write_pixels(directory, request, pixels)
        return
    from .local_grade_source import has_groups, verify_snapshot, check_export_decode
    from . import effect_recovery_runtime as recovery
    from . import manual_liquify_runtime as manual
    from . import studio_background_runtime as studio
    from . import id_background_runtime as id_background
    from . import optics_runtime as optics
    from . import sky_replacement_runtime as sky
    from .local_mask_state import file_stamp
    group_source_stamp = file_stamp(path) if has_groups(snap) else None
    recovery_source_stamp = file_stamp(path)
    manual_source_stamp = file_stamp(path)
    verify_snapshot(snap, path, tuple(reversed(request['source_size'])))
    recovery.verify_snapshot(snap, path, tuple(reversed(request['source_size'])))
    manual.verify_snapshot(snap, path, tuple(reversed(request['source_size'])))
    studio.verify_snapshot(snap, path, tuple(reversed(request['source_size'])))
    id_background.verify_snapshot(snap, path, tuple(reversed(request['source_size'])))
    optics.verify_snapshot(snap,path,tuple(reversed(request['source_size'])))
    sky.verify_snapshot(snap,path,tuple(reversed(request['source_size'])))
    decoded = _decode_original(path, request['max_source_pixels'])
    if [decoded.w, decoded.h] != request['source_size']:
        raise ValueError('Full decode dimensions differ from admitted source')
    if source_identity(path) != before:
        raise ValueError('Inspection source changed during decode')
    check_export_decode(snap, path, group_source_stamp, (decoded.h, decoded.w))
    recovery.check_export_decode(snap, path, recovery_source_stamp, (decoded.h, decoded.w))
    manual.check_export_decode(snap, path, manual_source_stamp, (decoded.h, decoded.w))
    from .fringe_repair_render import check_export_decode as fringe_decode
    fringe_decode(snap,path,manual_source_stamp,(decoded.h,decoded.w))
    studio.check_export_decode(snap, path, manual_source_stamp, (decoded.h, decoded.w))
    id_background.check_export_decode(snap, path, manual_source_stamp, (decoded.h, decoded.w))
    optics.check_export_decode(snap,path,manual_source_stamp,(decoded.h,decoded.w))
    sky.check_export_decode(snap,path,manual_source_stamp,(decoded.h,decoded.w))
    from . import body_pose_render as body_render
    body_render.check_export_decode(snap,path,manual_source_stamp,(decoded.h,decoded.w))
    from .hand_shape_runtime import check_export_decode as hand_shape_decode
    hand_shape_decode(snap,path,manual_source_stamp,(decoded.h,decoded.w))
    from .reference_color_runtime import verify_export as verify_reference
    verify_reference(snap,path,(decoded.h,decoded.w))
    if snap.get("grade_scope") == "objects":
        from .local_mask_state import check, verify_source
        verify_source(check(snap.get("local_masks")), path, (decoded.h, decoded.w))
        snap['local_mask_source_path'] = path
    spec, skipped = build_export_spec(snap, decoded.h, decoded.w, for_document=True)
    pixels = render_inspection_roi(decoded, spec, request['roi'],
        max_source_pixels=request['max_source_pixels'], max_display_pixels=request['max_display_pixels'],
        device='cpu', crop_rect=tuple(snap.get('crop_rect', (0,0,1,1))),
        rotation_degrees=float(snap.get('crop_rotation', 0)), skipped_layers=skipped)
    if [pixels.canvas_width, pixels.canvas_height] != request['canvas_size']:
        raise ValueError('Rendered canvas differs from admitted canvas')
    if source_identity(path) != before:
        raise ValueError('Inspection source changed during render')
    _write_pixels(directory, request, pixels)


def _write_pixels(directory, request, pixels):
    from .inspection_wire import encode_header
    header = encode_header(pixels, epoch=bytes.fromhex(request['epoch']),
        ticket=tuple(int(x) for x in request['ticket']), max_payload=request['max_display_pixels']*4)
    # Fixed private filenames only; never an export path supplied by the UI.
    partial = os.path.join(directory, 'result.part')
    with open(partial, 'xb', buffering=0) as out:
        offset = 0
        while offset < len(header):
            n = out.write(header[offset:])
            if not n:
                raise OSError('Inspection header write stalled')
            offset += n
        view = memoryview(pixels.rgba).cast('B')
        offset = 0
        while offset < len(view):
            n = out.write(view[offset:offset+1024*1024])
            if not n:
                raise OSError('Inspection result write stalled')
            offset += n
    os.replace(partial, os.path.join(directory, 'result.lrif'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--directory', required=True)
    ap.add_argument('--address-bytes', type=int, required=True)
    ap.add_argument('--output-bytes', type=int, required=True)
    ap.add_argument('--cpu-seconds', type=int, required=True)
    ap.add_argument('--parent-pid', type=int, required=True)
    args = ap.parse_args()
    bind_parent(args.parent_pid)
    limits(args.address_bytes, args.output_bytes, args.cpu_seconds)
    from .privacy import require_offline_or_exit
    require_offline_or_exit()
    try:
        render(args.directory)
    except Exception as exc:
        # Bounded diagnostic only. The parent treats nonzero exit as failure even
        # if allocation failure prevents this optional diagnostic being written.
        try:
            with open(os.path.join(args.directory, 'error.json'), 'x', encoding='utf-8') as out:
                json.dump({'error': type(exc).__name__ + ': ' + str(exc)[:2000]}, out)
        except Exception:
            pass
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
