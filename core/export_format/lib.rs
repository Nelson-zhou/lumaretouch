// SPDX-License-Identifier: GPL-3.0-or-later
//! Pure Original-format policy over authenticated host facts, not an encoder.
//!
//! No filesystem, hashing, decoding, allocation, queue or Python fallback. The
//! host owns source authentication and must freeze this result before admission.

pub const ABI_VERSION: u32 = 1;

// Input container IDs. Output codec/extension IDs use the same values, but
// canonical names are jpg/png/tif/webp, not the input aliases jpeg/tiff.
pub const UNKNOWN: u32 = 0;
pub const JPEG: u32 = 1;
pub const PNG: u32 = 2;
pub const TIFF: u32 = 3;
pub const WEBP: u32 = 4;

pub const BITMAP: u32 = 1;
pub const RAW: u32 = 2;
pub const ENCODED: u32 = 1;
pub const CREATIVE: u32 = 2;

pub const JPG8: u32 = 1 << 0;
pub const PNG8: u32 = 1 << 1;
pub const PNG16: u32 = 1 << 2;
pub const TIF8: u32 = 1 << 3;
pub const TIF16: u32 = 1 << 4;
pub const WEBP8: u32 = 1 << 5;
pub const ALL_CAPABILITIES: u32 = JPG8 | PNG8 | PNG16 | TIF8 | TIF16 | WEBP8;

pub const QUALITY: u32 = 1 << 0;
pub const TIFF_COMPRESSION: u32 = 1 << 1;
pub const GPS: u32 = 1 << 2;
pub const TARGET_SIZE: u32 = 1 << 3;

pub const INVALID_FACTS: u64 = 1;
pub const UNKNOWN_SOURCE_KIND: u64 = 2;
pub const RAW_UNSUPPORTED: u64 = 3;
pub const SOURCE_VARIANT_UNSUPPORTED: u64 = 4;
pub const CONTAINER_UNSUPPORTED: u64 = 5;
pub const SINGLE_FRAME_REQUIRED: u64 = 6;
pub const PRECISION_UNSUPPORTED: u64 = 7;
pub const WRITER_UNAVAILABLE: u64 = 8;

#[no_mangle]
pub extern "C" fn lrt_export_format_abi() -> u32 {
    ABI_VERSION
}

/// ABI 1, pointer-free: status:8, codec:8, precision:8, extension:8, options:4.
/// Reserved high bits are zero. A refusal contains only its nonzero status.
///
/// `single_frame` is 0 or 1; 0 includes unproven frame cardinality. All enum
/// fields use UNKNOWN=0. `precision` is the authenticated encoded precision,
/// never the display proxy depth or a RAW rendering precision. For a creative
/// asset, the host separately authenticates the encoded ancestor and binds the
/// effective creative pixels; the selected writer still uses ancestor facts.
#[no_mangle]
pub extern "C" fn lrt_export_format_resolve(
    container: u32,
    source_kind: u32,
    precision: u32,
    single_frame: u32,
    variant: u32,
    capabilities: u32,
) -> u64 {
    if container > WEBP
        || source_kind > RAW
        || single_frame > 1
        || variant > CREATIVE
        || capabilities & !ALL_CAPABILITIES != 0
    {
        return INVALID_FACTS;
    }
    if source_kind == RAW {
        return RAW_UNSUPPORTED;
    }
    if source_kind != BITMAP {
        return UNKNOWN_SOURCE_KIND;
    }
    if variant != ENCODED && variant != CREATIVE {
        return SOURCE_VARIANT_UNSUPPORTED;
    }
    if container == UNKNOWN {
        return CONTAINER_UNSUPPORTED;
    }
    if single_frame != 1 {
        return SINGLE_FRAME_REQUIRED;
    }
    let (required, options) = match (container, precision) {
        (JPEG, 8) => (JPG8, QUALITY | GPS | TARGET_SIZE),
        (PNG, 8) => (PNG8, QUALITY | GPS),
        (PNG, 16) => (PNG16, 0),
        (TIFF, 8) => (TIF8, TIFF_COMPRESSION | GPS),
        (TIFF, 16) => (TIF16, TIFF_COMPRESSION),
        (WEBP, 8) => (WEBP8, QUALITY | GPS),
        _ => return PRECISION_UNSUPPORTED,
    };
    if capabilities & required == 0 {
        return WRITER_UNAVAILABLE;
    }
    ((container as u64) << 8)
        | ((precision as u64) << 16)
        | ((container as u64) << 24)
        | ((options as u64) << 32)
}

#[cfg(test)]
mod tests;
