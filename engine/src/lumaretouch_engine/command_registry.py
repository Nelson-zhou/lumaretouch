"""Canonical command catalogue; handlers remain on the serialized engine owner."""
HANDLED = ("lens_blur", "expression_replacement", "fringe_repair", "fringe_repair_preview", "common_background", "common_background_preview", "common_background_readback", "creative_document", "canvas_guides", "project_recovery", "managed_import", "ingest_session", "workflow_owner", "project_package", "export_destination", "virtual_copy", "source_relocation", "preset_organisation", "colour_editor", "colour_editor_state", "colour_editor_sample", "photo_grain", "photo_grain_state", "photo_detail", "photo_detail_state", "photo_detail_receipt", "primary_calibration", "primary_calibration_state", "selective_colour", "selective_colour_state", "colour_grading", "colour_grading_state", "extended_tone", "extended_tone_state", "extended_tone_receipt", "hello", "hair_colour", "shoulder_shape", "leg_shape", "arm_shape", "waist_shape", "leg_length", "neck_shape", "torso_length", "waist_length", "head_size", "body_slim", "semantic_colour", "semantic_colour_cancel", "sample_library", "sample_library_cancel", "sky_semantic", "sky_replacement_preview", "optics_preview", "studio_background_preview", "manual_liquify_preview", "effect_recovery_preview", "local_grade_live", "inspection_snapshot", "color_scopes", "color_capture", "source_patch_capture", "prompted_masks", "white_balance_capture", "color_picker_capture", "color_picker_probe", "bench_start", "bench_stop", "set_device", "shutdown",
           "load_image", "set_strength", "precompute", "inpaint", "source_patch", "clone_stamp", "local_masks", "effect_recovery", "manual_liquify", "studio_background", "optics", "sky_replacement", "light",
           "deform", "lut", "custom_lut", "grade", "export", "exposure", "white_balance", "color_picker", "hsl", "curves", "levels", "crop", "background",
           "compare", "session", "project", "task", "history", "preset", "batch",
           # 挑图（LNX-PICK-001）。它不在 EDIT_CMDS 里，所以既不进撤销栈也不打脏标记：
           # 它是读出来的一格旁注，不是一次编辑动作
           "face", "pick",
           # 眼牙增强（LNX-PORTRAIT-009）：它是一次编辑（进撤销栈、打脏标记），所以
           # 两个名单都要有它——上一轮加曝光时只改一边，得到的就是"拖完按撤销纹丝不动
           # 而 UI 一句也不说为什么"（CORE-006 为此专门加了一条用例）
           "enhance", "lip_makeup", "brow_shape", "nose_shape", "eye_shape", "mouth_shape", "people", "hair_colour", "fabric")
