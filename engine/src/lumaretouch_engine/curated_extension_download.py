"""Bounded resumable acquisition shared by reviewed curated model profiles.

No caller-provided URL, filename or executable content. Kept bytes are untrusted
until the entire pinned size and SHA256 match. Import/status never network.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time
import urllib.request
from urllib.parse import urlsplit
from . import prompted_model_manifest as M


def checked_url(url, profile=M):
    # An internal fixed-URL profile can only use that exact reviewed URL,
    # including redirects. Existing HF profiles keep their existing policy.
    fixed = getattr(profile, "FIXED_DOWNLOAD_URL", None)
    if fixed is not None:
        if url != fixed or not url.startswith("https://storage.googleapis.com/mediapipe-models/"):
            raise ValueError("Checkpoint URL differs from the fixed reviewed asset")
        return
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not (host == 'huggingface.co' or host.endswith('.huggingface.co') or host.endswith('.hf.co'))):
        raise ValueError('Checkpoint redirect is not an approved HTTPS model host')


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, profile=M):
        super().__init__()
        self.profile = profile

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl, self.profile)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def partial_path(base, profile=M):
    return Path(base).parent / ('.' + profile.CHECKPOINT_SHA256 + '.checkpoint-part')


def partial_size(base, profile=M):
    path = partial_path(base, profile)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return 0
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > profile.CHECKPOINT_SIZE_BYTES:
        raise ValueError('Unsafe or oversized retained checkpoint; no file was removed')
    return info.st_size


def acquire(base, *, emit, cancelled, profile=M):
    """Called under canonical model-owner lock with a bundled internal profile.

    Profile is never IPC/user URL input. The SAM default keeps existing callers.
    """
    path = partial_path(base, profile)
    count = partial_size(base, profile)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'r+b') as output:
        info = os.fstat(output.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != count:
            raise ValueError('Retained download changed before acquisition')
        digest = hashlib.sha256()
        while chunk := output.read(1024 * 1024):
            cancelled(); digest.update(chunk)
        # A completed interrupted transfer can be reused without any network.
        if count == profile.CHECKPOINT_SIZE_BYTES:
            emit('verifying', downloaded_bytes=count, total_bytes=count)
            if digest.hexdigest() == profile.CHECKPOINT_SHA256:
                return path
            output.seek(0); output.truncate(); count = 0; digest = hashlib.sha256()
        checked_url(profile.CHECKPOINT_URL, profile)
        headers = {'Accept-Encoding':'identity', 'User-Agent':'LumaRetouch-Curated-Extension/1'}
        if count:
            headers['Range'] = f'bytes={count}-'
        emit('checkpoint', downloaded_bytes=count, total_bytes=profile.CHECKPOINT_SIZE_BYTES, resume_bytes=count)
        request = urllib.request.Request(profile.CHECKPOINT_URL, headers=headers)
        opener = urllib.request.build_opener(Redirects(profile))
        started = time.monotonic()
        with opener.open(request, timeout=30) as response:
            code = response.status
            if code == 206:
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                if (not match or tuple(map(int, match.groups())) != (count, profile.CHECKPOINT_SIZE_BYTES-1, profile.CHECKPOINT_SIZE_BYTES)):
                    raise ValueError('Resume response does not match the pinned checkpoint range')
            elif code == 200:
                # Server ignored Range: restart rather than append duplicate bytes.
                output.seek(0); output.truncate(); count = 0; digest = hashlib.sha256()
            else:
                raise ValueError('Unexpected checkpoint response status')
            length = response.headers.get('Content-Length')
            if length is not None and int(length) != profile.CHECKPOINT_SIZE_BYTES-count:
                raise ValueError('Checkpoint response length differs from reviewed metadata')
            if response.headers.get('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Encoded checkpoint response is not supported')
            output.seek(count)
            while True:
                cancelled()
                if time.monotonic()-started > 3600:
                    raise TimeoutError('Checkpoint transfer timed out; verified-size partial retained for retry')
                chunk = response.read(min(1024*1024, profile.CHECKPOINT_SIZE_BYTES-count+1))
                if not chunk:
                    break
                if count+len(chunk) > profile.CHECKPOINT_SIZE_BYTES:
                    raise ValueError('Checkpoint exceeds its pinned byte budget')
                output.write(chunk); digest.update(chunk); count += len(chunk)
                output.flush()
                emit('checkpoint', downloaded_bytes=count, total_bytes=profile.CHECKPOINT_SIZE_BYTES)
            output.flush(); os.fsync(output.fileno())
        emit('verifying', downloaded_bytes=count, total_bytes=profile.CHECKPOINT_SIZE_BYTES)
        if count != profile.CHECKPOINT_SIZE_BYTES:
            raise ValueError('Checkpoint transfer interrupted; retained bytes may be resumed')
        if digest.hexdigest() != profile.CHECKPOINT_SHA256:
            # Corrupt data must not permanently poison the next range request.
            output.seek(0); output.truncate(); output.flush(); os.fsync(output.fileno())
            raise ValueError('Checkpoint SHA256 mismatch; untrusted partial reset, retry explicitly')
        return path
