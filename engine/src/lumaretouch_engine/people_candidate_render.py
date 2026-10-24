"""Prepare a portrait candidate through the shared exact full-source exporter."""


def validate(engine,row,candidate,*,decoration_authority=None):
    from .full_candidate_render import render
    from .virtual_copy_people import row_snapshot
    from .face_decoration_project import require_transition
    require_transition(engine,row_snapshot(engine,row),candidate,row=row,authority=decoration_authority)
    from .facial_sculpt_project import require_transition as require_sculpt_transition
    require_sculpt_transition(engine,row_snapshot(engine,row),candidate,row=row)
    version=engine._document_versions().version(row)
    render(engine,row,row['state'],version.document_id,str(version.revision),people_graph=candidate)
