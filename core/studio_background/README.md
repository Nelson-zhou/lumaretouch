# Studio background coverage worker

Written only, not built or run. See `docs/development/studio-background-scope.md` for UI, precision, lifecycle and all 19 control mappings.

Dependency-free Rust computes source-normalized elliptical strokes with smoothstep feather, per-dab pressure × flow and a distinct per-stroke opacity ceiling. Ordered adds/subtracts are returned as float32 bias/gain fields, so the same vectors can refine an automatic detection mask without destroying subtraction semantics. There is no RGB in this protocol.

Input is u32-LE length, SBM1, u32 W/H/stroke-count; each stroke is u8 operation, seven f64s (feather, flow, opacity, four axes), u32 point count and three f64s per point (x, y, pressure). Output SBF1 + u64 byte count + full bias f32 plane + gain f32 plane. Python validates source identity and complete recipe budgets; Rust independently validates finite parameters, dimensions, point/dab/work bounds and trailing bytes. Missing matching worker is a visible blocker.

Coverage is applied as base × gain + bias. Per-stroke opacity is not compounded by self-crossings; flow is accumulated first. Separate strokes can build coverage intentionally. Photographic inpainting and lighting operators are not implemented by this mask worker.
