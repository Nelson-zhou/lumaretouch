# Original-format native boundary — authored / UNRUN

The policy helper is `core/export_format`, ABI 1. Its canonical contract and
input/status/option tables are in `core/export_format/README.md` and
`core/export_format/export_format.h`.

## Exact component manifest

- `core/export_format/Cargo.toml` — dependency-free crate description.
- `core/export_format/lib.rs` — pure scalar policy resolver, no codec or I/O.
- `core/export_format/export_format.h` — C ABI and bitfield layout.
- `core/export_format/tests.rs` — authored Rust policy fixtures, UNRUN.
- `core/export_format/README.md` — contract, matrix and limitations.
- `engine/src/lumaretouch_engine/export_format_native.py` — ctypes marshalling,
  native readiness, stable refusal codes; no decision fallback.
- `engine/tests/test_export_format_native_unrun.py` — authored Python adapter
  and real-ABI matrix fixtures, UNRUN.
- `packaging/build-export-format.sh` — authored release build recipe, UNRUN.
- `packaging/stage-engine.sh` — stages the actual helper and corresponding
  source/header/manifest/fixtures/docs/licence.
- `NOTICE` — original implementation attribution and scope.

The parent export integration owns source authentication, capability collection,
strict nested frozen format plans, per-entry tasks, decode agreement, existing
writers, receipts and UI. This component does not independently prove them.

## Python-facing DTO

```python
resolve({
    'container': 'jpeg' | 'png' | 'tiff' | 'webp' | 'unknown',
    'source_kind': 'bitmap' | 'raw' | 'unknown',
    'precision': int,
    'single_frame': bool,
    'variant': 'encoded' | 'creative' | 'unknown',
    # Extra authenticated host fact fields are retained by the plan owner.
}, {
    'jpg8': bool, 'png8': bool, 'png16': bool,
    'tif8': bool, 'tif16': bool, 'webp8': bool,
}) -> {
    'codec': 'jpg' | 'png' | 'tif' | 'webp',
    'bits': 8 | 16,
    'extension': 'jpg' | 'png' | 'tif' | 'webp',
    'applicable_options': {
        'quality': bool, 'tiff_compression': bool,
        'gps': bool, 'target_size': bool,
    },
}
```

Capability keys are exact and each value must be `bool`; source facts may have
extra authentication fields, but the five consumed fact values are strictly
typed. The integer precision field rejects Python `bool`. A refusal raises
`ExportFormatError`, a `ValueError` with a stable `.code`.

`readiness()` returns `export_original_format_protocol: 1`,
`export_original_format_available: bool` and, when unavailable,
`export_original_format_reason: str`. This probes the actual library and ABI;
it is not a file-exists-only promise of policy availability. Writer-specific
capability collection is a separate host responsibility.

## Adversarial matrix and remaining acceptance

All following fixtures are **authored, not executed**:

| Case | Required behavior |
|---|---|
| JPEG8, PNG8/16, TIFF8/16, WebP8, encoded or bound creative | Exact canonical codec/extension and source precision |
| Missing matching writer, even with every other writer available | `original_writer_unavailable`, no fallback |
| TIFF-shaped RAW, RAW-derived creative, other RAW containers | `original_raw_unsupported`, no TIFF/JPEG reinterpretation |
| Unknown source kind/container/variant | Corresponding stable refusal, no partial decision |
| Multiframe or unproven frame count | `original_single_frame_required` |
| 1/2/4/10/12/14/24/32-bit source, unknown precision | `original_precision_unsupported` |
| JPEG16/WebP16 | Precision refusal, not a switch to TIFF |
| Missing or malformed capability/fact fields | Invalid host facts before native invocation |
| Missing or wrong-version native helper | Unavailable/mismatch; no Python decision fallback |
| Native refusal with nonzero decision fields, unknown status or reserved bits | Invalid native result |

Integration, compilation, import, real codec, corrupt-payload, visual, task
retry and packaging execution remain for the user's final local test owner.
These source fixtures are not evidence of runtime success.
