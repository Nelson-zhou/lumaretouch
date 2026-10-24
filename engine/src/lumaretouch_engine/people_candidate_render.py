"""Prepare a portrait candidate through the shared exact full-source exporter."""


def validate(engine,row,candidate):
    from .full_candidate_render import render
    from .virtual_copy_people import row_snapshot
    from .face_decoration_project import require_transition
    require_transition(engine,row_snapshot(engine,row),candidate,row=row)
    version=engine._document_versions().version(row)
    render(engine,row,row['state'],version.document_id,str(version.revision),people_graph=candidate)
