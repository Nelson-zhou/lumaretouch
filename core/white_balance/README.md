# White-balance scalar foundation

Not integrated into the product. Legacy Python WB remains untouched. The current
file is an independently written pure Rust mathematical candidate with no image,
filesystem, subprocess, network or third-party runtime dependency. CI is configured to execute its
unit tests. Candidate 0c452175 passed all seven tests in CI39723480395 (0.05s, no skips). Root does not run product code locally.

- Correct CIE D daylight coefficients, explicit XYZ→linear-sRGB basis, the existing
  tint calibration and positive-temperature=cooler ratio convention.
- Exact unit gains at zero manual adjustment; explicit invalid-domain rejection.
- Y-preserving replacement neutral gains from an already-defined linear mean.
  Action sample noise/clipping/gain limits, geometry and provenance are NOT supplied
  by this math module and cannot be bypassed merely because a vector is finite.
- A sampled domain grid is a regression test, not a proof over every real number.
- No production algorithm capability, picker button or project version is enabled.

Sources of mathematical definitions/fixtures (not copied application code):
- W3C CSS Color4 CRD2026-10-20 conversion matrices:
  https://www.w3.org/TR/2026/CRD-css-color-4-20261020/#color-conversion-code
- Colour CIE D documented example and polynomial:
  https://colour.readthedocs.io/en/latest/_modules/colour/temperature/cie_d.html
- Exact community source pins, migration and acceptance obligations are in
  docs/development/white-balance-versioning-plan.md.

Before integration, choose and verify the bounded Python/Rust scalar ABI, preserve
legacy rendering, implement complete state/preset/project/export migration, and
close all picked-only bypass paths. Do not use a slow whole-image JSON bridge.

Before freezing the algorithm identifier, add independent combined temperature/
tint RGB-gain fixtures. Existing direction/identity/domain tests do not establish
full independent numerical parity for that composition.

## Bridge integration candidate

The existing packaged math helper now has a bounded `white-balance-v1` scalar
command with strict action, argument-count and reply validation. Python recipe
installation prepares an immutable gain vector once; NumPy/Torch frame processing
consumes the vector without spawning a process. A 256-entry scalar cache is bounded.
Legacy calls remain on their unchanged numerical path. Picked-only vectors activate
the low-level preview stage and invalid preparation leaves its old state intact.

These low-level hooks are NOT a completed user feature. Server state, project and
preset migration, frozen export/batch, undo and UI must be wired before enabling
corrected recipes. The current bridge change adds a test-only independent Decimal
oracle and actual helper/stage tests, which passed on d6b401af in CI39738251607: 16 cases, no skips, in1.24s.
