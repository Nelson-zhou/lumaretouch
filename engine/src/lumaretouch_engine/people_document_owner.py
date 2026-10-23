"""Document identity transport, separate from source bytes and person capsules.

Only native host selection, exact retained state identity, or an explicitly
selected document row can establish the owner. A copied portrait descriptor
cannot choose its own document, including for byte-identical virtual copies.
"""


def capture(engine,state,source_path,*,document_id=None,context_supplied=False):
    from .virtual_copy_people import current_row
    rows=getattr(engine,'_docs',[])
    if document_id is not None:
        matches=[row for row in rows if row.get('document_id')==document_id]
        if len(matches)!=1 or matches[0].get('path')!=source_path:
            raise ValueError('Portrait export document is unavailable or changed source path')
        row=matches[0]
    else:
        matches=[row for row in rows if row.get('state') is state]
        if len(matches)>1:raise ValueError('Portrait state has ambiguous document ownership')
        row=matches[0] if matches else None
        if row is None and not context_supplied:
            # Active capture is owned by the actual host selection, never by
            # searching other documents for matching source bytes or paths.
            current=current_row(engine)
            if current is not None and current.get('path')==source_path:row=current
        if row is None:return None
        if row.get('path')!=source_path:
            raise ValueError('Portrait export state belongs to another source path')
    return engine._document_versions().version(row).document_id


def validate_snapshot(people,document_id):
    if people is None:return
    if people.get('document_id')!=document_id:
        raise ValueError('Frozen portrait snapshot belongs to another document')
    from .people_cross_owner import validate_owner
    validate_owner(people['state'],people['asset_sha256'],document_id)
