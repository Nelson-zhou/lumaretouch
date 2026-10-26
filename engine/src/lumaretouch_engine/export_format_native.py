"""Original-format policy ABI, not an encoder or a source-fact authority.

Only authenticated host facts enter this adapter. Source identity, capability
discovery, option validation, frozen plan hashing and decoding belong to their
existing host owners. A missing/incompatible library refuses; never fall back
to a Python codec decision, runtime compilation, JPEG or an 8-bit writer.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path

ABI_VERSION = 1
CONTAINERS = {'unknown': 0, 'jpeg': 1, 'png': 2, 'tiff': 3, 'webp': 4}
SOURCE_KINDS = {'unknown': 0, 'bitmap': 1, 'raw': 2}
VARIANTS = {'unknown': 0, 'encoded': 1, 'creative': 2}
CODECS = {1: 'jpg', 2: 'png', 3: 'tif', 4: 'webp'}
CAPABILITY_KEYS = ('jpg8', 'png8', 'png16', 'tif8', 'tif16', 'webp8')
OPTION_KEYS = ('quality', 'tiff_compression', 'gps', 'target_size')
REFUSALS = {
    1: 'original_invalid_host_facts',
    2: 'original_source_kind_unknown',
    3: 'original_raw_unsupported',
    4: 'original_source_variant_unsupported',
    5: 'original_container_unsupported',
    6: 'original_single_frame_required',
    7: 'original_precision_unsupported',
    8: 'original_writer_unavailable',
}
MESSAGES = {
    'original_invalid_host_facts': '原格式缺少可信源事实或收到无效宿主能力',
    'original_source_kind_unknown': '无法认证来源是已编码位图；请选择明确导出格式',
    'original_raw_unsupported': '原格式不支持相机 RAW 或 RAW 派生来源；不会重写 RAW',
    'original_source_variant_unsupported': '无法认证当前来源变体与已编码原图的关系',
    'original_container_unsupported': '原图容器不在支持范围；不会替换为 JPEG',
    'original_single_frame_required': '原格式仅支持已认证的单帧来源',
    'original_precision_unsupported': '原图编码位深无法原生保留；不会降到 8-bit',
    'original_writer_unavailable': '所需原生编码器不可用；不会改格式或降低位深',
    'original_policy_unavailable': '原格式 Rust 策略核心未安装或不可加载',
    'original_policy_abi_mismatch': '原格式 Rust 策略核心版本不兼容',
    'original_policy_invalid_result': '原格式 Rust 策略核心返回无效决策',
}


class ExportFormatError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'{MESSAGES.get(code, code)} ({code})')


@lru_cache(maxsize=1)
def _native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_export_format.so'
    if not path.is_file():
        raise ExportFormatError('original_policy_unavailable')
    try:
        library = C.CDLL(str(path))
        library.lrt_export_format_abi.argtypes = []
        library.lrt_export_format_abi.restype = C.c_uint32
        library.lrt_export_format_resolve.argtypes = [C.c_uint32] * 6
        library.lrt_export_format_resolve.restype = C.c_uint64
    except (OSError, AttributeError) as error:
        raise ExportFormatError('original_policy_unavailable') from error
    if library.lrt_export_format_abi() != ABI_VERSION:
        raise ExportFormatError('original_policy_abi_mismatch')
    return library


def readiness():
    """Probe the installed ABI, not just file existence; never build or download."""
    try:
        _native()
    except (ValueError, OSError, RuntimeError) as error:
        return {'export_original_format_protocol': ABI_VERSION,
                'export_original_format_available': False,
                'export_original_format_reason': str(error)}
    return {'export_original_format_protocol': ABI_VERSION,
            'export_original_format_available': True}


def resolve(facts, capabilities):
    """Return the native codec/bits/extension/applicability decision, or refuse.

    facts may contain extra frozen authentication fields. This function only
    marshals the six policy fields and cannot authenticate a document by itself.
    `precision` is encoded source precision, not a preview's sample depth.
    """
    if (type(facts) is not dict or type(capabilities) is not dict
            or set(capabilities) != set(CAPABILITY_KEYS)
            or any(type(capabilities[key]) is not bool for key in CAPABILITY_KEYS)):
        raise ExportFormatError('original_invalid_host_facts')
    for key, choices in (('container', CONTAINERS), ('source_kind', SOURCE_KINDS),
                         ('variant', VARIANTS)):
        if type(facts.get(key)) is not str or facts[key] not in choices:
            raise ExportFormatError('original_invalid_host_facts')
    if (type(facts.get('precision')) is not int or not 0 <= facts['precision'] <= 0xffffffff
            or type(facts.get('single_frame')) is not bool):
        raise ExportFormatError('original_invalid_host_facts')
    capability_bits = sum(1 << index for index, key in enumerate(CAPABILITY_KEYS) if capabilities[key])
    encoded = int(_native().lrt_export_format_resolve(
        CONTAINERS[facts['container']], SOURCE_KINDS[facts['source_kind']],
        facts['precision'], int(facts['single_frame']), VARIANTS[facts['variant']], capability_bits))
    status = encoded & 255
    if status:
        if encoded != status or status not in REFUSALS:
            raise ExportFormatError('original_policy_invalid_result')
        raise ExportFormatError(REFUSALS[status])
    codec, bits, extension, options = ((encoded >> shift) & 255 for shift in (8, 16, 24, 32))
    if (encoded >> 36 or codec not in CODECS or extension != codec
            or bits not in (8, 16) or options & ~15):
        raise ExportFormatError('original_policy_invalid_result')
    return {'codec': CODECS[codec], 'bits': bits, 'extension': CODECS[extension],
            'applicable_options': {key: bool(options & (1 << index))
                                   for index, key in enumerate(OPTION_KEYS)}}
