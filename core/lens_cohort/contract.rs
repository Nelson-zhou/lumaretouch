// SPDX-License-Identifier: GPL-3.0-or-later
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub abi_version:u32, pub struct_size:u32, pub aperture:u32,
    pub max_radius_px:f32, pub focus_near:f32, pub focus_far:f32,
    pub depth_falloff:f32, pub occlusion_tolerance:f32, pub rotation_radians:f32,
    pub manual_depth:f32, pub manual_depth_ack:u32,
}
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct Budget {
    pub abi_version:u32, pub struct_size:u32,
    pub max_fft_butterflies:u64, pub max_kernel_quadrature_evals:u64,
    pub max_classification_pixels:u64, pub max_support_probes:u64,
    pub max_direct_pairs:u64, pub reserved_repair_pairs:u64,
    pub max_scratch_bytes:u64, pub max_sink_bytes:u64,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct Plan {
    pub abi_version:u32, pub struct_size:u32, pub math_identity:u32,
    pub non_delta_cohort_count:u32,
    pub width:u64, pub height:u64, pub source_pixels:u64,
    pub validation_pixels:u64, pub classification_pixels:u64,
    pub repeated_halo_classification_pixels:u64,
    pub tile_width:u64, pub tile_height:u64, pub tile_columns:u64, pub tile_count:u64,
    pub fft_width:u64, pub fft_height:u64, pub kernel_quadrature_evals:u64,
    pub fft_transform_count:u64, pub fft_butterflies:u64,
    pub residual_emitters:u64, pub residual_candidate_pairs:u64,
    pub residual_quadrature_upper_bound:u64, pub support_probe_upper_bound:u64,
    pub repair_candidate_reservation:u64, pub direct_pair_upper_bound:u64,
    pub owned_plan_bytes:u64, pub required_scratch_bytes:u64,
    pub borrowed_source_bytes:u64, pub borrowed_refinement_bytes:u64,
    pub sink_bytes:u64, pub output_tile_bytes:u64,
}
