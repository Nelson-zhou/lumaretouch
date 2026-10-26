// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: dependency-free policy vectors, not codec validation.
use super::*;

fn fields(value: u64) -> (u64, u64, u64, u64, u64) {
    (value & 255, (value >> 8) & 255, (value >> 16) & 255,
     (value >> 24) & 255, value >> 32)
}

#[test]
fn supported_encoded_and_creative_matrix_preserves_precision() {
    for variant in [ENCODED, CREATIVE] {
        for (container, bits, capability, options) in [
            (JPEG, 8, JPG8, QUALITY | GPS | TARGET_SIZE),
            (PNG, 8, PNG8, QUALITY | GPS),
            (PNG, 16, PNG16, 0),
            (TIFF, 8, TIF8, TIFF_COMPRESSION | GPS),
            (TIFF, 16, TIF16, TIFF_COMPRESSION),
            (WEBP, 8, WEBP8, QUALITY | GPS),
        ] {
            let result = lrt_export_format_resolve(container, BITMAP, bits, 1, variant, capability);
            assert_eq!(fields(result), (0, container as u64, bits as u64, container as u64, options as u64));
        }
    }
}

#[test]
fn no_other_codec_or_precision_capability_can_substitute() {
    for (container, bits, needed) in [
        (JPEG, 8, JPG8), (PNG, 8, PNG8), (PNG, 16, PNG16),
        (TIFF, 8, TIF8), (TIFF, 16, TIF16), (WEBP, 8, WEBP8),
    ] {
        assert_eq!(lrt_export_format_resolve(container, BITMAP, bits, 1, ENCODED,
                   ALL_CAPABILITIES & !needed), WRITER_UNAVAILABLE);
    }
}

#[test]
fn unsupported_precisions_never_become_eight_bit() {
    for container in [JPEG, PNG, TIFF, WEBP] {
        for bits in [0, 1, 2, 4, 10, 12, 14, 24, 32, u32::MAX] {
            assert_eq!(lrt_export_format_resolve(container, BITMAP, bits, 1, ENCODED,
                       ALL_CAPABILITIES), PRECISION_UNSUPPORTED);
        }
    }
    for container in [JPEG, WEBP] {
        assert_eq!(lrt_export_format_resolve(container, BITMAP, 16, 1, ENCODED,
                   ALL_CAPABILITIES), PRECISION_UNSUPPORTED);
    }
}

#[test]
fn raw_and_unknown_sources_have_no_partial_decision() {
    for container in [UNKNOWN, JPEG, PNG, TIFF, WEBP] {
        for variant in [UNKNOWN, ENCODED, CREATIVE] {
            assert_eq!(lrt_export_format_resolve(container, RAW, 16, 1, variant,
                       ALL_CAPABILITIES), RAW_UNSUPPORTED);
        }
    }
    assert_eq!(lrt_export_format_resolve(TIFF, UNKNOWN, 16, 1, ENCODED,
               ALL_CAPABILITIES), UNKNOWN_SOURCE_KIND);
    assert_eq!(lrt_export_format_resolve(UNKNOWN, BITMAP, 8, 1, ENCODED,
               ALL_CAPABILITIES), CONTAINER_UNSUPPORTED);
    assert_eq!(lrt_export_format_resolve(PNG, BITMAP, 8, 1, UNKNOWN,
               ALL_CAPABILITIES), SOURCE_VARIANT_UNSUPPORTED);
    assert_eq!(lrt_export_format_resolve(PNG, BITMAP, 8, 0, ENCODED,
               ALL_CAPABILITIES), SINGLE_FRAME_REQUIRED);
}

#[test]
fn malformed_enum_boolean_or_reserved_capability_is_invalid() {
    for args in [
        [5, BITMAP, 8, 1, ENCODED, ALL_CAPABILITIES],
        [PNG, 3, 8, 1, ENCODED, ALL_CAPABILITIES],
        [PNG, BITMAP, 8, 2, ENCODED, ALL_CAPABILITIES],
        [PNG, BITMAP, 8, 1, 3, ALL_CAPABILITIES],
        [PNG, BITMAP, 8, 1, ENCODED, 1 << 6],
    ] {
        assert_eq!(lrt_export_format_resolve(args[0], args[1], args[2], args[3], args[4], args[5]), INVALID_FACTS);
    }
    assert_eq!(lrt_export_format_abi(), 1);
}
