# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow derived-source admission for retained recovery alias reviews. UNRUN.

Wire validation does not authorize a source or recovery mutation. The ordinary
derived guard still checks actual pipeline pixels, capture and selected face;
this extension additionally requires the existing exact alias review object.
"""


def check_request(name, request):
    if 'protocol' not in request:
        return False
    from .eye_bag_recovery_alias_controller import check_preview_request, check_apply_request
    if name == 'effect_recovery':
        check_apply_request(request)
    elif name == 'effect_recovery_preview':
        check_preview_request(request)
    else:
        raise ValueError('Derived alias recovery version cannot authorize another command')
    return True


def require_record(engine, record, request):
    if 'protocol' not in request:
        return
    if (type(record) is not dict or record.get('target') != 'eye_bag_preserve'
            or record.get('eye_bag_alias_entry') is None):
        raise ValueError('Derived alias recovery requires its retained eye-bag-only review')
    from .eye_bag_recovery_alias_review import verify
    verify(engine, record['eye_bag_alias_entry'])
