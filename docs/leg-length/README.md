# Long-leg control tranche: implemented source, not accepted runtime

Baseline: manual-text.txt lines 561–567 and AI开发资料包/功能需求验收映射.json
5250–5294. Official https://wiki.pixcakeai.com/guide/9412.html reviewed 2026-10-23:
length controls at 144–154 describe overall leg elongation with separate thigh
and calf lengths. Width controls are different controls. No official numeric
limits, left/right unlocking or background protection are inferred.

| Requirement | Original implementation | Acceptance |
| --- | --- | --- |
| LNX-REF-PC-32473-C-d79658697a | atomic set of thigh+calf, never third warp | UNRUN |
| LNX-REF-PC-32473-C-eefc19db17 | hip-to-knee longitudinal endpoint extension | UNRUN |
| LNX-REF-PC-32473-C-17fb085b4c | knee-to-ankle longitudinal endpoint extension | UNRUN |

The Rust forward displacement uses actual hip→knee and knee→ankle vectors, not
transverse liquify. At hip displacement=0; at knee=dT; at ankle=dT+dC; throughout
reviewed complete foot plateau displacement=dT+dC. Quintic Hermite segments make
the field C2 at hip/knee/ankle/foot transitions. Above hip the torso remains fixed.
The reviewed lateral silhouette plateau is constant in x; C2 lateral background
falloff and the explicitly reviewed below-foot return bring it to identity.
Consequently segment endpoint distances increase independently by the requested
fraction, with neither a third overall warp nor a width proxy. Foot shape is
translated, not stretched, inside its reviewed plateau.

Original local policy: UI 0–100, default 0, maximum endpoint extension 8% per
segment, both sides controlled together. Global gradient bound ≤0.45 proves
contraction and prevents folding for the admitted field. Off-grid inverse uses
up to 64 fixed-point iterations, residual ≤1e-7 pixels, inverse determinant gates,
and conservative 128-render-pixel displacement budget. These are implementation
limits, not vendor specifications or naturalness acceptance. A high-resolution
export may explicitly refuse a displacement that fits the preview budget; it
must never clamp strength or silently export a different result.

Real33 pose and reviewed visible silhouette/background support are required.
Near-upright segments only (horizontal/depth delta ≤35% vertical delta), ≥32px
vertical extent, explicit visible heels/toes, complete original frame, disjoint
left/right support corridors and room below feet. Crossed, bent, cropped,
foreshortened, hidden-joint/foot or unsupported transition cases are rejected,
not supplied guessed anatomy. This is deliberately conservative capability,
not full-body AI, height control, waist length or torso-length support.

All source/BodyRef/analysis/model/pose digests and operation-specific immutable
reviews are preserved. Export takes original RGB8/RGB16/float32 HDR without a
local image warp. Shared source sampling also transforms the existing face,
hair, masks and recovery fields. Host/history/transfer modules retain current
uncertain-result query-only semantics and explicit target review. The portable
recipe contains only two numeric parameters, never source measurements.

Interactive panel includes distinct controls, mixed overall display, reset,
source-only support picker, seven explicit confirmations, pending/uncertain
states and no replay. Native workflow and all shared routes are authored as recorded in INTEGRATION.md.
Source wiring is not a claim of successful compilation, execution or acceptance.

No product execution, product imports, tests, build, compiler, typecheck, inference,
install, download, Git write or push was performed. Only source reading/writing,
Python AST syntax parsing, JSON inspection and content hashing are allowed here.
Rust and UI test cases are authored, not run. Photographic naturalness, large-file
performance and target-machine regression remain Qoder/local acceptance work.
