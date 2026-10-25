"""Prepare a portrait candidate through the shared exact full-source exporter."""


def validate(engine,row,candidate,*,decoration_authority=None):
    from .full_candidate_render import render
    from .virtual_copy_people import row_snapshot
    from .face_decoration_project import require_transition
    require_transition(engine,row_snapshot(engine,row),candidate,row=row,authority=decoration_authority)
    from .facial_sculpt_project import require_transition as require_sculpt_transition
    require_sculpt_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .eye_makeup_enhance_project import require_transition as require_eye_makeup_enhance_transition
    require_eye_makeup_enhance_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .hair_unification_project import require_transition as require_hair_unification_transition
    require_hair_unification_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .hair_volume_project import require_transition as require_hair_volume_transition
    require_hair_volume_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .skin_reference_match_project import require_transition as require_reference_transition
    require_reference_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .skin_reference_body_project import require_transition as require_body_reference_transition
    require_body_reference_transition(engine,row_snapshot(engine,row),candidate,row=row)
    from .neck_wrinkle_project import require_parked_transition
    require_parked_transition(row_snapshot(engine,row),candidate)
    version=engine._document_versions().version(row)
    render(engine,row,row['state'],version.document_id,str(version.revision),people_graph=candidate)
