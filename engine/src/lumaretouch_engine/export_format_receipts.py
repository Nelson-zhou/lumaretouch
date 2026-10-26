"""Authenticate already committed variants for same-plan, same-session retry.

This is not a writer or a second task ledger. Only complete existing writer
receipts may be reused, after an exact path/stat/content check. Uncertain commits
remain failures; output names never change and nothing is overwritten.
"""
from hashlib import sha256
import os
import stat

SCHEMA = 'lrt.export-encoded-output.v1'
MAX_BYTES = 4 * 1024 * 1024 * 1024


def identity(path):
    from .export_destination_policy import absolute
    path = absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        stream_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(stream_fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
                raise ValueError('original_output_receipt_file_bounds')
            hashed, size = sha256(), 0
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('original_output_receipt_byte_limit')
                hashed.update(chunk)
            stamp = lambda value: [value.st_dev, value.st_ino, value.st_size,
                                    value.st_mtime_ns, value.st_ctime_ns]
            after = os.fstat(stream.fileno())
            if (size != before.st_size or stamp(before) != stamp(after)
                    or stamp(after) != stamp(os.stat(path, follow_symlinks=False))):
                raise ValueError('original_output_changed_during_receipt')
            return {'schema':SCHEMA, 'path':str(path), 'file_stamp':stamp(after),
                    'bytes':size, 'sha256':hashed.hexdigest()}
    finally:
        os.close(fd)


def reusable(output, target, decision):
    if (output.get('path') != target or output.get('skipped') or output.get('error') or output.get('verification_failed')
            or output.get('durability_confirmed') is False or output.get('directory_fsync') is False
            or output.get('committed') is False or output.get('bytes', 0) <= 0
            or output.get('format') != decision['codec'] or output.get('bits') != decision['bits']
            or output.get('decision_id') != decision['decision_id'] or output.get('fact_id') != decision['fact_id']
            or not isinstance(output.get('output_identity'), dict)):
        return False
    if (output['output_identity'].get('sha256') != (output.get('encoded_sha256') or output.get('sha256'))
            or output['output_identity'].get('bytes') != output['bytes']):
        return False
    if output['output_identity'] != identity(target):
        raise ValueError('Original 已提交副本被替换或改变；不会覆盖、改名或假装完成')
    return True
