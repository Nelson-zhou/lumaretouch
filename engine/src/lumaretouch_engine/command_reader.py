# SPDX-License-Identifier: GPL-3.0-or-later
"""Selectable stdin reader, extracted from Engine.run without editor ownership.

One queued command retains existing backpressure. An optional ingress may consume
cancellation-only controls; ordinary commands always execute on the engine thread.
"""
import os
import queue
import select


def read_commands(input_fd, wake_read, inbox, stopped, *, ingress=lambda line: False,
                  on_eof=lambda: None):
    def enqueue(line):
        if isinstance(line, str) and line and ingress(line): return True
        while not stopped.is_set():
            try:
                inbox.put(line, timeout=.05)
                return True
            except queue.Full:
                pass
        return False

    pending = bytearray()
    try:
        while not stopped.is_set():
            ready, _, _ = select.select([input_fd, wake_read], [], [])
            if wake_read in ready: return
            chunk = os.read(input_fd, 65536)
            if not chunk:
                if pending and not enqueue(pending.decode('utf-8')): return
                on_eof()
                enqueue('')
                return
            pending.extend(chunk)
            while True:
                newline = pending.find(b'\n')
                if newline < 0: break
                line = pending[:newline + 1].decode('utf-8')
                del pending[:newline + 1]
                if not enqueue(line): return
    except Exception as exc:
        on_eof()
        enqueue({'read_error': str(exc)})
