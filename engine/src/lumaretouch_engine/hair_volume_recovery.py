# SPDX-License-Identifier: GPL-3.0-or-later
"""Hair-volume canonical graph boundary, not an alternative undo owner.

AUTHORED / UNRUN. Read failures and exact no-ops do not dirty a project. An
uncertain graph publication cannot be autosaved as a verified committed graph.
"""

def finish(engine, boundary, error):
    request = boundary['message']
    if request.get('cmd') != 'hair_volume':
        return False
    if request.get('action') not in ('commit', 'clear') or not boundary['started']:
        return True
    runtime = engine.__dict__.get('_project_recovery_runtime')
    if runtime is None:
        return True
    from .hair_volume_support import digest
    record = engine.__dict__.get('_hair_volume_receipts', {}).get(request.get('request_id'), {})
    terminal = record.get('result') or {}
    exact = (record.get('digest') == digest(request)
             and terminal.get('request_id') == request.get('request_id')
             and terminal.get('action') == request.get('action')
             and terminal.get('people_context') == request.get('people_context')
             and terminal.get('request_payload') == request.get('payload'))
    changed = engine._people_owner().fence != boundary.get('hair_volume_before_fence')
    if exact and terminal.get('outcome_unknown') is False:
        if terminal.get('success') is True and not error and boundary['returned']:
            if changed:
                runtime.revision += 1
            return True
        if not changed:
            return True  # A rejected command did not alter this canonical graph.
    if not runtime.tainted:
        runtime.tainted = True
        runtime.reason = '发量原提交尚未确认，请查询原请求或重新打开已确认的工程'
    return True
