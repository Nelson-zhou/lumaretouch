# Lens blur acceptance fixtures: UNRUN

All fixtures listed below are authored expectations, not observed results. The
source lives in `core/lens_aperture/tests.rs`; no test/build/import was executed.

## Native synthetic fixture manifest

| Fixture | Expected contract | Status |
|---|---|---|
| zero_radius_is_bitwise_identity_including_negative_zero | Exact signed/HDR/alpha copy | UNRUN |
| every_depth_in_focus_is_bitwise_identity | Focus interval neutral | UNRUN |
| depth_radius_uses_interval_distance_not_focal_length | Source radius and signed correction formula | UNRUN |
| circular_aperture_is_flat_inside_and_compact_not_gaussian | Disk, not Gaussian | UNRUN |
| radius_one_impulse_matches_independent_midpoint_counts | Independent 16:8:1 aperture counts | UNRUN |
| five_original_kernels_are_pairwise_distinct | Five actual distinct kernels | UNRUN |
| cat_eye_rotation_changes_support_axis_but_not_disk | Rotation affects geometric support | UNRUN |
| constant_signed_hdr_and_partial_alpha_survive_all_apertures | No SDR clipping or alpha loss | UNRUN |
| transparent_constant_remains_canonical_zero | Premultiplied transparent output | UNRUN |
| transparent_boundary_blurs_premultiplied_colour_and_alpha_together | No straight-alpha colour leak | UNRUN |
| farther_emitter_cannot_contaminate_opaque_focused_foreground | Depth occlusion gate | UNRUN |
| near_defocused_emitter_can_spread_over_far_receiver | Source radius, front-to-back asymmetry | UNRUN |
| alpha_visibility_rule_is_exact_and_explicit | Partial-alpha attenuation equation | UNRUN |
| explicit_clear_receiver_is_exact_even_beside_near_blur | Exact clear brush endpoint | UNRUN |
| tile_boundaries_use_full_source_halo_and_equal_monolithic | Horizontal/vertical seam parity | UNRUN |
| invalid_depth_and_refinement_never_publish_even_when_neutral | Validation not skipped | UNRUN |
| noncanonical_alpha_and_hdr_are_rejected_without_clipping | Strict canonical float contract | UNRUN |
| settings_and_resource_limits_are_fail_closed | Unsupported IDs/overflow/cost reject | UNRUN |
| cancellation_before_and_during_work_preserves_all_output | No partial tile publication | UNRUN |
| full_validation_detects_bad_data_outside_a_rendered_tile | Snapshot/halo validation distinction | UNRUN |
| ffi_detects_partial_alias_without_constructing_mutable_slice | Partial overlap reject | UNRUN |
| ffi_null_optional_plane_requires_zero_length | Null optional-plane contract | UNRUN |
| ffi_abi_and_struct_layout_match_header | Version/capability/layout contract | UNRUN |

## Real-image acceptance pack still required

Use only generated or explicitly authorized images. Record exact source pixels,
depth provenance, model/runtime pins where applicable, operation recipe and
hashes of the actual produced output. Required scenes include:

- A sharply focused portrait before point lights, hair and glasses boundaries.
- A near defocused fence/foliage over a sharp far subject; inspect hard-inner-edge
  and asymmetric-spread artifacts from the current visibility approximation.
- Multi-person different-depth portraits, clicked focus on each subject, changed
  focus interval and restored original source/recipe.
- Fine hair, translucent veil and low-alpha cutout against bright/black backgrounds.
- Signed wide-range working values, saturated HDR light points, 16-bit gradients.
- Cat-eye/polygon rotation, tiny and large radius, moving strength slider and
  pixel-scale sparkles to expose deterministic quadrature stepping.
- Image edges, odd dimensions, narrow rows, multiple independently rendered tiles.
- Clear/blur strokes with every radius/flow/feather combination, undo/redo,
  source switch, crop/rotate/warp, cancellation, stale completion and close/reopen.
- Batch and full-size export with unavailable depth/native modules, retained saved
  recipes, precise failure reports and no proxy-resolution masquerading as source.

For each, keep intended behavior separate from observed output. Synthetic
success would not prove photographic quality, optical accuracy or parity with
PixCake; a screenshot cannot prove full-resolution export or state integrity.
