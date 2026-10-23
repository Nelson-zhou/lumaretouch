"""Decorate one existing history entry with each independent ownership domain."""
def decorate(before,after):
    from .people_document_history import decorate as people
    from .body_pose_document_history import decorate as bodies
    return bodies(people(before,after),after)
