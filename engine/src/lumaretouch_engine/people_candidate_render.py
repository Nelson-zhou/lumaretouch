"""Prepare a portrait candidate through the shared exact full-source exporter."""


def validate(engine,row,candidate):
    from .full_candidate_render import render
    version=engine._document_versions().version(row)
    render(engine,row,row['state'],version.document_id,str(version.revision),people_graph=candidate)
