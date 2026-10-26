"""Restore saved export snapshots through the existing project codec, never live edits.

No new queue/journal: only saved project/recovery snapshots have durable authority.
Unknown commit windows, relocated sources and unsupported dependency proofs block.
"""
from copy import deepcopy
from dataclasses import fields
from hashlib import sha256
from pathlib import Path
import os

from . import tasks as T
from .export_destination_policy import digest

SCHEMA = 'lrt.export-task-snapshot.v1'
MAX_NODES = 65536
MAX_BYTES = 128 * 1024 * 1024


def _json_bounds(value):
    """Bound raw JSON before canonical hashing or any project asset decoding."""
    import math
    nodes, text_bytes = 0, 0
    def walk(item, depth=0):
        nonlocal nodes, text_bytes
        nodes += 1
        if nodes > MAX_NODES or depth > 64: raise ValueError('Task JSON structural budget exceeded')
        if item is None or type(item) is bool: return
        if type(item) is int:
            if item.bit_length() > 128: raise ValueError('Task integer exceeds scalar budget')
        elif type(item) is float:
            if not math.isfinite(item): raise ValueError('Nonfinite task scalar')
        elif type(item) is str:
            if len(item) > 8 * 1024 * 1024: raise ValueError('Task string exceeds budget')
            text_bytes += len(item.encode('utf-8'))
            if text_bytes > 8 * 1024 * 1024: raise ValueError('Task text budget exceeded')
        elif type(item) is list:
            for child in item: walk(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str: raise ValueError('Task JSON keys must be strings')
                walk(key, depth + 1); walk(child, depth + 1)
        else: raise ValueError('Task envelope must contain plain JSON values')
    walk(value)


def _asset_bounds(encoded, assets):
    """Count every reference before decode, including PNG decoded pixel dimensions."""
    import base64
    import re
    import struct
    if type(assets) is not dict: raise ValueError('Invalid project asset bank')
    budget = 0
    widths = {'uint8':1, 'uint16':2, 'uint32':4, 'uint64':8,
              'int8':1, 'int16':2, 'int32':4, 'int64':8,
              'float16':2, 'float32':4, 'float64':8}
    known = _types()
    def charge(reference):
        nonlocal budget
        if type(reference) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', reference) is None:
            raise ValueError('Invalid asset reference')
        row = assets.get(reference)
        if type(row) is not dict or set(row) != {'kind', 'shape', 'dtype', 'bytes', 'b64'}:
            raise ValueError('Unsupported task asset record')
        size, data = row['bytes'], row['b64']
        if (type(size) is not int or not 0 <= size <= 16 * 1024 * 1024 or type(data) is not str
                or len(data) != 4 * ((size + 2) // 3)):
            raise ValueError('Task encoded asset exceeds byte budget')
        kind, shape, dtype = row['kind'], row['shape'], row['dtype']
        if type(kind) is not str or kind not in ('raw', 'png', 'bytes', 'custom-cube'):
            raise ValueError('Unsupported task asset kind')
        decoded_size = size
        if kind in ('raw', 'png'):
            if (type(shape) is not list or not 1 <= len(shape) <= 4
                    or any(type(n) is not int or not 0 <= n <= 32768 for n in shape)
                    or type(dtype) is not str or dtype not in widths):
                raise ValueError('Invalid task array dtype/dimensions')
            count = 1
            for n in shape: count *= n
            decoded_size = count * widths[dtype]
            if kind == 'raw' and decoded_size != size: raise ValueError('Raw array byte mismatch')
            if kind == 'png':
                if (dtype != 'uint8' or len(shape) not in (2, 3) or not all(shape)
                        or len(shape) == 3 and shape[2] not in (1, 3, 4) or size < 33):
                    raise ValueError('Unsupported PNG array shape')
                header = base64.b64decode(data[:44], validate=True)
                if header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
                    raise ValueError('Invalid PNG array header')
                width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', header[16:29])
                channels = 1 if len(shape) == 2 else shape[2]
                if ((height, width) != tuple(shape[:2]) or depth != 8
                        or colour != {1:0, 3:2, 4:6}[channels]
                        or (compression, filtering, interlace) != (0, 0, 0)):
                    raise ValueError('PNG header disagrees with bounded array metadata')
                decoded_size = width * height * 4  # Decoder scratch conservatively charged.
        elif shape is not None or dtype is not None:
            raise ValueError('Byte asset has unexpected array metadata')
        # Base64 raw + decoder/copy buffers; repeated references are NOT deduplicated.
        budget += size * 2 + decoded_size * 3
        if budget > MAX_BYTES: raise ValueError('Task decoded asset allocation budget exceeded')
    def walk(item):
        if type(item) is dict:
            rejected = {'__creative_bytes__', '_creative_base', '_creative_asset_records',
                '_local_grade_layers', '_effect_recovery', '_manual_liquify', '_brow_shape',
                '_eye_shape', '_primary_calibration', '_colour_editor', '_selective_colour',
                '_colour_grading', '_photo_grain', '_portrait_protection', '_photo_detail',
                '_extended_tone', '_reference_color', '_semantic_colour', '_body_pose_bank',
                '_mouth_shape', '_nose_shape', '_lip_makeup', '_optics', '_sky_replacement',
                '_id_background', '_studio_background'}
            if rejected.intersection(item):
                raise ValueError('Specialized project record recovery is not admitted')
            if any(key.startswith('__') and key not in ('__asset__', '__dc__', '__custom_cube__') for key in item):
                raise ValueError('Unknown task codec tag')
            if '__asset__' in item:
                if set(item) != {'__asset__', 'at'} or type(item['at']) is not str:
                    raise ValueError('Invalid encoded asset tag')
                charge(item['__asset__'])
            if '__dc__' in item:
                if (set(item) != {'__dc__', 'fields'} or type(item['__dc__']) is not str
                        or item['__dc__'] not in known or type(item['fields']) is not dict
                        or set(item['fields']) != {f.name for f in fields(known[item['__dc__']])}):
                    raise ValueError('Unknown or incomplete task dataclass tag')
            for child in item.values(): walk(child)
        elif type(item) is list:
            for child in item: walk(child)
    walk(encoded)


def _args_structure(args):
    if type(args) is not tuple or len(args) != 10:
        raise ValueError('Invalid frozen export argument tuple')
    images, out_dir, fmt, quality, tile, doc, snap, bits, opts, by_path = args
    if (type(images) is not list or not images or any(type(key) is not str or not key for key in images)
            or type(out_dir) is not str or type(fmt) is not str or type(quality) is not int
            or type(tile) is not int or doc is not None and type(doc) is not str
            or type(snap) is not dict or type(opts) is not dict or type(by_path) is not dict
            or type(opts.get('document_entries')) is not dict):
        raise ValueError('Invalid frozen export argument field types')
    if len(images) != len(set(images)) or set(images) != set(by_path) or set(images) != set(opts['document_entries']):
        raise ValueError('Frozen selection identity mismatch')
    for key in images:
        pair, entry = by_path[key], opts['document_entries'][key]
        if (type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not dict or type(pair[1]) is not bool
                or type(entry) is not dict or type(entry.get('path')) is not str
                or type(entry.get('document_id')) is not str or type(entry.get('source_asset_id')) is not str
                or type(entry.get('fingerprint')) is not dict):
            raise ValueError('Invalid frozen document/snapshot fields')
    plan = opts.get('destination_plan')
    if type(plan) is not dict or type(plan.get('entries')) is not list:
        raise ValueError('Invalid frozen destination structure')
    for entry in plan['entries']:
        if (type(entry) is not dict or type(entry.get('source_stamp')) not in (list, tuple)
                or type(entry.get('missing_directories')) not in (list, tuple)
                or any(type(entry.get(key)) is not str for key in ('item_id', 'source_path', 'target', 'disposition'))):
            raise ValueError('Invalid frozen destination entry fields')


def dependencies():
    from .project import writer_stamp
    from importlib import metadata
    versions = writer_stamp()
    for name in ('scipy', 'opencv-python', 'onnxruntime', 'mediapipe'):
        try: versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError: versions[name] = None
    # Engine version alone is not a code identity in developer installations.
    root = Path(__file__).parent
    sources = {}
    for path in sorted(root.rglob('*.py')):
        if len(sources) >= 4096 or path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Export recovery code dependency inventory exceeds bounds')
        sources[str(path.relative_to(root))] = sha256(path.read_bytes()).hexdigest()
    import platform
    import sys
    # Bounded local provenance, not a claim of cross-hardware pixel equivalence.
    # Reuse already loaded runtime facts; never import a model or scan weights.
    torch = sys.modules.get('torch')
    if torch is None:
        raise ValueError('Loaded runtime build provenance is unavailable')
    cpu = {}
    with open('/proc/cpuinfo', 'r', encoding='utf-8') as stream:
        for line in stream.read(1024 * 1024).splitlines():
            key, separator, value = line.partition(':')
            if separator and key.strip() in ('vendor_id', 'model name', 'flags', 'microcode'):
                cpu.setdefault(key.strip(), value.strip())
    if not cpu.get('model name') or not cpu.get('flags'):
        raise ValueError('CPU provenance is unavailable')
    runtime = {'system': platform.system(), 'machine': platform.machine(),
        'libc': list(platform.libc_ver()), 'python_build': list(platform.python_build()),
        'python_compiler': platform.python_compiler(), 'byteorder': sys.byteorder,
        'cpu': cpu, 'torch_build': torch.__config__.show(),
        'torch_threads': torch.get_num_threads(), 'torch_interop_threads': torch.get_num_interop_threads(),
        'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
        'mkldnn_enabled': torch.backends.mkldnn.enabled,
        'environment': {key: os.environ.get(key) for key in
            ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_CBWR', 'ONEDNN_MAX_CPU_ISA')}}
    _json_bounds(runtime)
    return {'versions': versions, 'engine_sources': digest(sources), 'runtime': runtime}


def origin(host, task):
    """Creation only; never infer old task authority from the project being saved."""
    task['_recovery_origin'] = deepcopy(task['_control_owner'])
    try: task['_recovery_dependencies'] = dependencies()
    except (ValueError, OSError) as error: task['_recovery_error'] = str(error)


def _types():
    from .vram import RepairOp, LightOp
    from .face import FacePrecompute
    from .ops.lut import CubeLut
    return {cls.__name__: cls for cls in (RepairOp, LightOp, FacePrecompute, CubeLut)}


def _shape(value, tuple_paths=None):
    """Tagged path segments cannot collide with user dictionary keys.

    Restoration uses only decoded known classes, no arbitrary imports or pickle.
    Every supplied tuple path must be consumed exactly once.
    """
    restore = tuple_paths is not None
    if restore:
        if type(tuple_paths) is not list or len(tuple_paths) > MAX_NODES:
            raise ValueError('Invalid tuple shape inventory')
        wanted = set()
        for path in tuple_paths:
            if type(path) is not list or len(path) > 64:
                raise ValueError('Invalid tuple path')
            for segment in path:
                if (type(segment) is not list or len(segment) != 2
                        or segment[0] not in ('key', 'field', 'index')
                        or (segment[0] == 'index' and (type(segment[1]) is not int or segment[1] < 0))
                        or (segment[0] != 'index' and type(segment[1]) is not str)):
                    raise ValueError('Invalid tuple path segment')
            key = tuple(tuple(segment) for segment in path)
            if key in wanted: raise ValueError('Duplicate tuple shape path')
            wanted.add(key)
    else: wanted = set()
    found, nodes = [], 0
    known = tuple(_types().values())
    def walk(item, path=()):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or len(path) > 64: raise ValueError('Tuple shape budget exceeded')
        if type(item) is dict:
            result = {key: walk(child, path + (('key', key),)) for key, child in item.items()}
        elif type(item) in (list, tuple):
            children = [walk(child, path + (('index', i),)) for i, child in enumerate(item)]
            if restore:
                result = tuple(children) if path in wanted else children
                if path in wanted: wanted.remove(path)
            else:
                if type(item) is tuple: found.append([list(segment) for segment in path])
                result = item
        elif type(item) in known:
            children = {field.name: walk(getattr(item, field.name), path + (('field', field.name),)) for field in fields(item)}
            result = type(item)(**children) if restore else item
        else: result = item
        if restore and path in wanted: raise ValueError('Tuple shape points to a non-list')
        return result
    result = walk(value)
    if restore and wanted: raise ValueError('Unconsumed tuple shape path')
    return result if restore else found


def _owned(args):
    from .render_snapshot import own_render_inputs
    return own_render_inputs({'args': args}, max_asset_bytes=MAX_BYTES,
                             max_nodes=MAX_NODES).value['args']


def _admit(host, args):
    """Deliberately bounded first dependency contract: CPU global edits only.

    Keep every unsupported recipe/asset encoded, but do not offer unsafe replay.
    The shared complete neutral gate proves other feature families inactive.
    """
    _args_structure(args)
    images, _, _, _, _, _, snap, _, opts, by_path = args
    if not images or len(images) != len(set(images)) or set(images) != set(by_path):
        raise ValueError('Frozen export selection mismatch')
    if not opts.get('destination_plan'): raise ValueError('Legacy output has no authenticated frozen destination plan')
    if snap.get('export_layout'): raise ValueError('Layout aggregate recovery proof is not yet supported')
    if opts.get('_trusted_destination_roots'):
        raise ValueError('Owned workflow lease must be restored by its workflow owner')
    if opts.get('output_profile') not in ('none', 'source', 'srgb'):
        raise ValueError('Custom ICC recovery is not yet admitted')
    from .export_destination_policy import restore
    plan = restore(opts['destination_plan'])
    if set(e.item_id for e in plan.entries) != set(images):
        raise ValueError('Derivative/watermarked output recovery requires an aggregate proof')
    if snap.get('export_watermark'): raise ValueError('Watermark asset recovery is not yet admitted')
    from .master16_policy import Master16PolicyMixin
    from .ops import curves, levels
    from . import white_balance_recipe as WB
    for key in images:
        local, for_document = by_path[key]
        if not for_document: raise ValueError('External paths lack authenticated document ownership')
        for field in ('_bg', 'deform', 'enhance', 'params', 'light'):
            if type(local.get(field)) is not dict:
                raise ValueError('Invalid frozen feature dictionary: ' + field)
        if local.get('body_pose') is not None or local.get('people') is not None:
            raise ValueError('People/body graphs need additional restored ownership proof')
        if any(local.get(field) is not None for field in ('creative_base', 'hand_shape', 'hand_tone', 'limb_vein', 'fabric_sweat')):
            raise ValueError('Source-bound feature recovery is not admitted')
        if local.get('device') != 'cpu' or host.device != 'cpu':
            raise ValueError('Recovery currently requires the original CPU device; no implicit device fallback')
        # These global scalar families do not require external model weights.
        neutral = dict(local)
        neutral.update(grade=(0., 0., 0., 1.), exposure=(0.,) * 7,
            exposure_ref_k=None, wb_options=WB.default_options(), hsl=(0.,) * 24,
            curves=curves.default_curves(), levels=levels.default_levels(),
            crop_rect=(0., 0., 1., 1.), crop_rotation=0., sharpen=0.)
        if local.get('grade_scope') != 'all' or local.get('channel') is not None:
            raise ValueError('Scoped/model-generated masks need additional dependency proof')
        if Master16PolicyMixin._master16_snapshot_blockers(neutral):
            raise ValueError('Recipe requires additional model/feature recovery dependency proof')
    return plan


def serialize(host, project):
    from . import project as PJ
    from .optics_candidate_identity import fingerprint
    rows = []
    with host._task_lock:
        frozen = [(deepcopy(task), host._task_args.get(task['task_id'])) for task in host._tasks.values()]
    for task, args in frozen:
        row = T.for_json(task)
        origin_value = task.get('_recovery_origin')
        # Never launder a task from another project/workspace at save time.
        from .export_task_controls import current_owner
        if (args is None or origin_value is None or origin_value.get('project_id') != project['project_id']
                or task.get('_control_owner') != current_owner(host)):
            row['recovery_blocked'] = 'No same-owner retained recipe snapshot; legacy/foreign task remains read-only'
            rows.append(row); continue
        row.pop('recovery', None)
        try:
            if task.get('_recovery_error'): raise ValueError(task['_recovery_error'])
            owned = _owned(args)
            dropped, assets = [], dict(project['assets'])
            encoded = PJ.encode({'args': owned}, assets, dropped, 'task.snapshot')
            if dropped: raise ValueError('Task snapshot codec dropped unsupported values')
            shape = _shape({'args': owned})
            decoded = PJ.decode(encoded, assets, dropped, 'task.snapshot', dc_types=_types())
            decoded = _shape(decoded, shape)['args']
            if dropped or fingerprint(decoded, exact=True) != fingerprint(owned, exact=True):
                raise ValueError('Task snapshot did not round-trip exactly')
            body = {'schema': SCHEMA, 'task_id': task['task_id'],
                'project_id': origin_value['project_id'], 'origin': origin_value,
                'dependencies': task['_recovery_dependencies'], 'inputs_sha256': digest(task['inputs']),
                'items_sha256': digest(task['items']),
                'encoded': encoded, 'tuple_paths': shape, 'snapshot_sha256': fingerprint(owned, exact=True)}
            row['recovery'] = {**body, 'digest': digest(body)}
            row.pop('recovery_blocked', None)
            project['assets'] = assets
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as error:
            row['recovery_blocked'] = str(error)
        rows.append(row)
    return rows


def verify(host, task, args):
    """Recheck dependencies and receipts before any state transition or worker."""
    if task.get('_recovery_dependencies') != dependencies():
        raise ValueError('Engine/runtime dependency identity changed; fixed-input recovery refused')
    plan = _admit(host, args)
    entries = args[8]['document_entries']
    documents = {row['document_id']: row for row in host._docs}
    from .virtual_copy_source import verify_entry
    cache = set()
    for key in args[0]:
        entry = entries[key]
        row = documents.get(entry.get('document_id'))
        if (not row or row['path'] != entry['path'] or row.get('source_asset_id') != entry.get('source_asset_id')
                or (entry.get('fingerprint') or {}).get('hash_level') != 'full'):
            raise ValueError('Frozen source/document ownership changed or relocated')
        verify_entry(entry, cache)
    if args[2] == 'original':
        from .export_format_plan import worker_decision
        for key in args[0]: worker_decision(args[8], key, entries[key], args[9][key][0])
    targets = {entry.item_id: entry for entry in plan.entries}
    from .export_format_receipts import identity
    for item in task['items']:
        target = targets[item['path']]
        proofs = [output for output in item.get('outputs', []) if output.get('path') == target.target
                  and output.get('recovery_plan_id') == plan.plan_id and output.get('output_identity')]
        if target.disposition != 'write':
            if item['state'] == T.SUCCEEDED: raise ValueError('Succeeded receipt conflicts with frozen skip disposition')
            continue
        if os.path.lexists(target.target):
            if len(proofs) != 1 or not complete(proofs[0]) or identity(target.target) != proofs[0]['output_identity']:
                raise ValueError('Existing output has missing/changed/uncertain commit proof; never overwrite or rename')
            if item['state'] != T.SUCCEEDED:
                raise ValueError('Output committed but item completion is uncertain; explicit reconciliation required')
        elif item['state'] == T.SUCCEEDED or proofs:
            raise ValueError('Previously committed output is missing; never silently recreate it')
    return args


def complete(output):
    if type(output) is not dict or type(output.get('output_identity')) is not dict:
        return False
    if type(output.get('bytes')) is not int:
        return False
    proof = output['output_identity']
    if (set(proof) != {'schema', 'path', 'file_stamp', 'bytes', 'sha256'}
            or type(proof['path']) is not str or type(proof['sha256']) is not str
            or type(proof['bytes']) is not int or type(proof['file_stamp']) is not list
            or len(proof['file_stamp']) != 5 or any(type(n) is not int for n in proof['file_stamp'])):
        return False
    return (not any(output.get(key) for key in ('error', 'skipped', 'verification_failed'))
        and output.get('committed') is not False and output.get('durability_confirmed') is not False
        and output.get('directory_fsync') is not False and output.get('bytes', 0) > 0
        and proof.get('bytes') == output['bytes']
        and proof.get('sha256') == (output.get('encoded_sha256') or output.get('sha256')))


def restore(host, project, task):
    from . import project as PJ
    from .optics_candidate_identity import fingerprint
    value = task.get('recovery')
    if type(value) is not dict: raise ValueError(task.get('recovery_blocked') or 'Legacy task has no persisted frozen recipe')
    _json_bounds(value)
    _json_bounds(task['inputs'])
    _json_bounds(task['items'])
    required = {'schema', 'task_id', 'project_id', 'origin', 'dependencies', 'inputs_sha256',
                'encoded', 'tuple_paths', 'snapshot_sha256', 'items_sha256', 'digest'}
    if set(value) != required or value['schema'] != SCHEMA or type(value['origin']) is not dict:
        raise ValueError('Invalid task snapshot envelope')
    if (set(value['origin']) != {'project_id', 'workspace_generation', 'session_id'}
            or any(type(v) is not str or not v for v in value['origin'].values())
            or type(value['dependencies']) is not dict or type(value['encoded']) is not dict
            or type(value['tuple_paths']) is not list):
        raise ValueError('Invalid task snapshot provenance/container fields')
    if (digest({k:v for k,v in value.items() if k != 'digest'}) != value['digest']
            or value['task_id'] != task['task_id'] or value['project_id'] != project['project_id']
            or value['origin'].get('project_id') != project['project_id']
            or value['inputs_sha256'] != digest(task['inputs'])
            or value['items_sha256'] != digest(task['items'])):
        raise ValueError('Task snapshot identity/ownership integrity mismatch')
    _asset_bounds(value['encoded'], project['assets'])
    dropped = []
    decoded = PJ.decode(value['encoded'], project['assets'], dropped, 'task.snapshot', dc_types=_types())
    if type(decoded) is not dict or set(decoded) != {'args'}:
        raise ValueError('Invalid decoded task snapshot root')
    args = _shape(decoded, value['tuple_paths'])['args']
    _args_structure(args)
    if dropped or fingerprint(args, exact=True) != value['snapshot_sha256']:
        raise ValueError('Frozen task recipe/assets failed exact integrity check')
    args = _owned(args)
    if set(item['path'] for item in task['items']) != set(args[0]):
        raise ValueError('Task item selection differs from frozen snapshot')
    task['_recovery_origin'] = deepcopy(value['origin'])
    task['_recovery_dependencies'] = deepcopy(value['dependencies'])
    verify(host, task, args)
    task['_restored_snapshot'] = True
    return args
