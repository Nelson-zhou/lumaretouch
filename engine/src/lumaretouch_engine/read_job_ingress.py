# SPDX-License-Identifier: GPL-3.0-or-later
"""Reader-thread read-job controls, extracted without changing order or owners."""
def stop(engine):
    from .portrait_crop_controller import controller as crop_jobs
    crop_jobs(engine).stop()
    engine._background_material_host().stop()
    from .creative_selection_jobs import controller as selection_jobs
    selection_jobs(engine).stop()
    from .light_glow_jobs import controller as glow_jobs
    glow_jobs(engine).stop()
    from .lens_blur_jobs import controller as lens_jobs
    lens_jobs(engine).stop()
    from .expression_replacement_jobs import controller as expression_jobs
    expression_jobs(engine).stop()
    from .eye_bag_review_jobs import controller as eye_bag_jobs
    eye_bag_jobs(engine).stop()
    engine._photo_detail_service().stop()
    engine._extended_tone_service().stop()
    engine._photo_grain_service().stop()
    engine._colour_grading_service().stop()
    engine._primary_calibration_service().stop()
    engine._selective_colour_service().stop()
    engine._colour_editor_service().stop()
    owner = engine.__dict__.get("_custom_lut_owner")
    if owner is not None:
        with owner.lock:
            for key, event in owner.events.items():
                if not (owner.active == key and owner.published): event.set()
    engine._owned_reader_stop()

def ingress(engine, line):
    from .portrait_crop_controller import controller as crop_jobs
    if crop_jobs(engine).ingress(line): return True
    if engine._background_material_host().observe_line(line): return True
    from .creative_selection_jobs import controller as selection_jobs
    selection_jobs(engine).ingress(line)
    from .light_glow_jobs import controller as glow_jobs
    if glow_jobs(engine).ingress(line): return True
    from .lens_blur_jobs import controller as lens_jobs
    if lens_jobs(engine).ingress(line): return True
    from .expression_replacement_jobs import controller as expression_jobs
    if expression_jobs(engine).ingress(line): return True
    from .eye_bag_review_jobs import controller as eye_bag_jobs
    if eye_bag_jobs(engine).ingress(line): return True  # Cancellation control cannot invalidate unrelated edit owners.
    primary_consumed=engine._primary_calibration_service().ingress(line)
    selective_consumed=engine._selective_colour_service().ingress(line)
    editor_consumed=engine._colour_editor_service().ingress(line)
    grain_consumed=engine._photo_grain_service().ingress(line)
    grading_consumed=engine._colour_grading_service().ingress(line)
    detail_consumed=engine._photo_detail_service().ingress(line)
    tone_consumed=engine._extended_tone_service().ingress(line)
    lut_consumed=engine._custom_lut_service().ingress(line)
    owned_consumed=engine._owned_command_ingress(line)
    return editor_consumed or detail_consumed or primary_consumed or selective_consumed or grain_consumed or grading_consumed or tone_consumed or lut_consumed or owned_consumed
