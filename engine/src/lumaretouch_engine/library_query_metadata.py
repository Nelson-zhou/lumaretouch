"""Small genuine source facts, extracted only during existing decode work.

No additional image load, stat, file hash, inference or pixel allocation. RAW
decoders that do not expose EXIF produce unknown capture time, not file mtime.
"""
from datetime import datetime, timedelta, timezone
import os
import re
from .library_query_schema import canonical_format

MAX_EXIF_BYTES = 4 * 1024 * 1024


def exif_capture(raw):
    unknown = {'capture_time': None, 'capture_time_source': 'unavailable',
               'capture_time_zone': 'unknown'}
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_EXIF_BYTES:
        return unknown
    try:
        from PIL import Image
        exif = Image.Exif()
        exif.load(raw)
        # DateTime (306) describes modification, not capture. Do not use it.
        values = dict(exif)
        try:
            values.update(exif.get_ifd(0x8769))
        except (KeyError, TypeError, ValueError, OSError):
            pass
        text = values.get(36867)  # DateTimeOriginal
        if isinstance(text, bytes):
            text = text.decode('ascii')
        if type(text) is not str:
            return unknown
        date = datetime.strptime(text.strip('\x00 '), '%Y:%m:%d %H:%M:%S')
        fraction = values.get(37521)  # SubSecTimeOriginal
        if isinstance(fraction, bytes):
            fraction = fraction.decode('ascii')
        if type(fraction) is str and re.fullmatch(r'\d{1,12}', fraction.strip('\x00 ')):
            date = date.replace(microsecond=int((fraction.strip('\x00 ') + '000000')[:6]))
        offset = values.get(36881)  # OffsetTimeOriginal
        if isinstance(offset, bytes):
            offset = offset.decode('ascii')
        zone = 'unspecified'
        if type(offset) is str and re.fullmatch(r'[+-]\d{2}:\d{2}', offset.strip('\x00 ')):
            offset = offset.strip('\x00 ')
            hours, minutes = int(offset[1:3]), int(offset[4:6])
            if hours <= 23 and minutes <= 59:
                delta = timedelta(hours=hours, minutes=minutes)
                date = date.replace(tzinfo=timezone(delta if offset[0] == '+' else -delta))
                zone = offset
        return {'capture_time': date.isoformat(), 'capture_time_source': 'exif_original',
                'capture_time_zone': zone}
    except (ValueError, TypeError, OSError, UnicodeError, OverflowError, SyntaxError):
        return unknown


def decoded_facts(decoded):
    return {**exif_capture(getattr(decoded, 'source_exif', None)),
            'format': canonical_format(getattr(decoded, 'fmt', None)),
            'format_source': 'decoder',
            'src_w': getattr(decoded, 'src_w', None),
            'src_h': getattr(decoded, 'src_h', None)}


def capture_decoded(row, decoded):
    """Call at an existing successful decode publication point, not on query."""
    row['_library_metadata'] = decoded_facts(decoded)
    if row.get('_local_source_stamp') is not None:
        row['_library_source_stamp'] = tuple(row['_local_source_stamp'])


def capture_file_identity(row):
    """Call once at row creation; query execution itself never stats the file."""
    try:
        stat = os.stat(row['path'])
        row['_library_source_stamp'] = (stat.st_dev, stat.st_ino, stat.st_size,
                                        stat.st_mtime_ns, stat.st_ctime_ns)
    except OSError:
        row['_library_source_stamp'] = None
