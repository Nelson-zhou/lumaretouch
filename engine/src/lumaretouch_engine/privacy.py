"""Linux engine-process offline boundary, applied before accepting commands.

This restricts this process and its threads/children only. It does not change host
network settings. Library imports alone do not install a filter; the shipped
server entry point does. This is not a general malicious-code filesystem sandbox.
"""
from __future__ import annotations
import ctypes as C
import errno
import os
import stat
import sys

_DENIED = ('socket','connect','sendto','sendmsg','sendmmsg','io_uring_setup')
_STATUS = None


class OfflinePolicyError(RuntimeError):
    pass


def policy_status():
    return dict(_STATUS) if _STATUS is not None else {'enforced': False, 'scope': 'engine_process'}


def _close_inherited_sockets():
    """write(2) on an inherited network descriptor would bypass send* restrictions."""
    closed=0
    for entry in os.listdir('/proc/self/fd'):
        fd=int(entry)
        try: mode=os.fstat(fd).st_mode
        except OSError as exc:
            if exc.errno==errno.EBADF:continue  # /proc directory handle already closed
            raise
        if stat.S_ISSOCK(mode):
            if fd<=2:
                raise OfflinePolicyError('engine stdio must use pipes/files, not network sockets')
            os.close(fd);closed+=1
    return closed


def _native_probe():
    # Native calls prove this is not merely a Python API monkeypatch. No address
    # is supplied and no connection/data is sent, even if enforcement is broken.
    libc=C.CDLL(None,use_errno=True)
    create=libc.socket;create.argtypes=[C.c_int,C.c_int,C.c_int];create.restype=C.c_int
    for family in (2,10):  # Linux AF_INET / AF_INET6
        C.set_errno(0);fd=create(family,1,0)
        if fd>=0:
            os.close(fd)
            raise OfflinePolicyError('native offline self-check failed; refusing to start')
        if C.get_errno()!=errno.EPERM:
            raise OfflinePolicyError('native offline denial was not verified')


def install_offline_policy():
    """Fail closed if the kernel cannot enforce all-thread, inherited denial.

    SCMP_FLTATR_CTL_TSYNC=4 is the public libseccomp enum. NNP is explicitly
    enabled. Unknown syscall names or any filter failure prevent startup.
    """
    global _STATUS
    if _STATUS is not None:return dict(_STATUS)
    if not sys.platform.startswith('linux'):
        raise OfflinePolicyError('the engine offline boundary requires Linux')
    try:
        lib=C.CDLL('libseccomp.so.2')
    except OSError as exc:
        raise OfflinePolicyError('缺少 libseccomp2，无法保证引擎离线，已拒绝启动') from exc
    lib.seccomp_init.argtypes=[C.c_uint32];lib.seccomp_init.restype=C.c_void_p
    lib.seccomp_attr_set.argtypes=[C.c_void_p,C.c_uint,C.c_uint];lib.seccomp_attr_set.restype=C.c_int
    lib.seccomp_syscall_resolve_name.argtypes=[C.c_char_p];lib.seccomp_syscall_resolve_name.restype=C.c_int
    lib.seccomp_rule_add.argtypes=[C.c_void_p,C.c_uint32,C.c_int,C.c_uint];lib.seccomp_rule_add.restype=C.c_int
    lib.seccomp_load.argtypes=[C.c_void_p];lib.seccomp_load.restype=C.c_int
    lib.seccomp_release.argtypes=[C.c_void_p];lib.seccomp_release.restype=None
    ctx=lib.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW; only network capability is removed.
    if not ctx:raise OfflinePolicyError('cannot allocate offline filter')
    try:
        for attr in (3,4):  # CTL_NNP, CTL_TSYNC
            if lib.seccomp_attr_set(ctx,attr,1)!=0:
                raise OfflinePolicyError('kernel cannot enforce synchronized offline policy')
        for name in _DENIED:
            number=lib.seccomp_syscall_resolve_name(name.encode('ascii'))
            if number<0 or lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,number,0)!=0:
                raise OfflinePolicyError('cannot install complete offline syscall policy')
        if lib.seccomp_load(ctx)!=0:
            raise OfflinePolicyError('kernel rejected offline policy; refusing to start')
        # First synchronize the denial across threads, then close inherited
        # sockets. Closing first leaves a create-socket race before TSYNC.
        closed=_close_inherited_sockets()
    finally:
        lib.seccomp_release(ctx)
    _native_probe()
    _STATUS={'enforced':True,'scope':'engine_process','mechanism':'linux_seccomp',
             'thread_synchronized':True,'native_selfcheck':True,'closed_inherited_sockets':closed,
             'network_access':False}
    return dict(_STATUS)


def require_offline_or_exit():
    """Application entry-point guard; never continue with an unenforced policy."""
    try:
        return install_offline_policy()
    except (OfflinePolicyError, OSError) as exc:
        print('LumaRetouch offline boundary: '+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(2) from exc
