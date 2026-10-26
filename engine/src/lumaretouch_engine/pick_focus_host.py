# SPDX-License-Identifier: GPL-3.0-or-later
"""Original review uses the existing pick worker, session rows and stop owner.

Transient evidence only. No project store, edit/history mutation or new queue.
"""
import threading
import time
from . import pick_original_focus as F


def active(engine):
    worker = getattr(engine, "_picks", None)
    return bool(worker is not None and getattr(worker, "_lrt_original_focus", False) and worker.is_alive())


def running(engine):
    """Wire state may be terminal while the thread retains admission ownership."""
    worker = getattr(engine, "_picks", None)
    return bool(worker is not None and worker.is_alive()
                and not getattr(worker, "_lrt_focus_terminal", False))


def _write(engine, row, path, **values):
    with engine._doclock:
        if row.get('path') != path or not any(r is row for r in engine._docs):
            return False
        row.update(values)
        return True


def start(engine, command, emit):
    try:
        if set(command) - {'cmd', 'action', 'indices', 'focus_x', 'focus_y', 'focus_documents'}:
            raise ValueError('Original focus accepts explicit indices and normalized review point only')
        indices = command.get('indices')
        if (type(indices) is not list or not 1 <= len(indices) <= F.MAX_TARGETS
                or any(type(i) is not int for i in indices) or len(set(indices)) != len(indices)):
            raise ValueError('Select 1 to 8 distinct photos for original focus review')
        document_ids = command.get('focus_documents')
        if (type(document_ids) is not list or len(document_ids) != len(indices)
                or any(type(v) is not str or not v for v in document_ids)):
            raise ValueError('Original review requires exact selected document identities')
        position = F.point(command.get('focus_x', .5), command.get('focus_y', .5))
        if engine._picks is not None and engine._picks.is_alive():
            raise ValueError('Pick worker is busy; stop or await it before original review')
        from .sample_library_capture import heavy_reason
        reason = heavy_reason(engine)
        if reason:
            raise ValueError(reason)
        for name in ('bench', '_export'):
            job = getattr(engine, name, None)
            if job is not None and job.is_alive():
                raise ValueError('Wait for benchmark/export before full-source review')
        inspection = getattr(engine, '_inspection', None)
        if inspection is not None and any(getattr(inspection, k, None) is not None for k in ('tx', 'result', 'job')):
            raise ValueError('Release full-resolution inspection before original review')
        with engine._doclock:
            if any(not 0 <= i < len(engine._docs) for i in indices):
                raise ValueError('Original review selection changed; refresh the library')
            if any(engine._docs[i].get('document_id') != doc_id
                   for i, doc_id in zip(indices, document_ids)):
                raise ValueError('Selected document identities changed; refresh before review')
            targets = [(engine._docs[i], engine._docs[i]['path'],
                        (engine._docs[i].get('src_w'), engine._docs[i].get('src_h'))
                        if engine._docs[i].get('opened') else None) for i in indices]
            # Explicit cache lifetime: only the latest bounded request retains
            # crops. Re-running proxy suggestions does not overwrite evidence.
            for row in engine._docs:
                row.pop('pick_focus', None)
                row.pop('pick_focus_error', None)
        engine._pick_stop.clear()
        worker = threading.Thread(target=_loop, args=(engine, targets, position, emit), daemon=True)
        worker._lrt_original_focus = True
        engine._picks = worker
        emit({'event': 'pick_start', 'action': 'focus', 'targets': len(targets),
              'scope': 'original-source-crop'})
        worker.start()
    except Exception as error:
        message = f'{type(error).__name__}: {error}'
        emit({'event': 'pick_failed', 'action': 'focus', 'error': message,
              'running': running(engine)})
        emit({'event': 'error', 'error': message})


def _loop(engine, targets, position, emit):
    start_time = time.monotonic()
    count = failed = 0
    try:
        for number, (row, path, size) in enumerate(targets):
            if engine._pick_stop.is_set():
                break
            try:
                # Source identity and row ownership are independent fences.
                with engine._doclock:
                    if row.get('path') != path or not any(r is row for r in engine._docs):
                        raise ValueError('Selected document was removed or relocated')
                result = F.review(path, known_size=size, position=position,
                                  cancelled=engine._pick_stop.is_set)
                if engine._pick_stop.is_set():
                    break
                if not _write(engine, row, path, pick_focus=result, pick_focus_error=None):
                    raise ValueError('Selected document changed before review publication')
                count += 1
            except InterruptedError:
                break
            except Exception as error:
                failed += 1
                message = f'{type(error).__name__}: {error}'
                _write(engine, row, path, pick_focus=None, pick_focus_error=message)
                # A per-row failure is progress, not terminal start rejection.
            emit({'event': 'pick_progress', 'action': 'focus', 'done': number+1,
                  'total': len(targets), 'failed': failed, 'count': count})
            engine.emit_session_state()
    finally:
        # Retain worker ownership until actual thread exit: a new start cannot
        # clear its stop token or publish before this terminal response. Override
        # only the final session wire status, not the shared worker reservation.
        threading.current_thread()._lrt_focus_terminal = True
        emit({'event': 'pick_done', 'action': 'focus', 'count': count, 'failed': failed,
              'groups': [], 'stopped': engine._pick_stop.is_set(),
              'total_ms': (time.monotonic()-start_time)*1000})
        engine.emit_session_state(picks_running=False)
