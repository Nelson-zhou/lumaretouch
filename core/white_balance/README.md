# White-balance scalar foundation

Integrated through the packaged scalar helper, versioned recipe state and explicit
algorithm/reset actions. Legacy Python WB remains unchanged. This independently
written pure Rust mathematical module has no image,
filesystem, subprocess, network or third-party runtime dependency. CI is configured to execute its
unit tests. Candidate 0c452175 passed all seven tests in CI39723480395 (0.05s, no skips). Root does not run product code locally.

- Correct CIE D daylight coefficients, explicit XYZ→linear-sRGB basis, the existing
  tint calibration and positive-temperature=cooler ratio convention.
- Exact unit gains at zero manual adjustment; explicit invalid-domain rejection.
- Y-preserving replacement neutral gains from an already-defined linear mean.
  Action sample noise/clipping/gain limits, geometry and provenance are NOT supplied
  by this math module and cannot be bypassed merely because a vector is finite.
- A sampled domain grid is a regression test, not a proof over every real number.
- Corrected mode is explicit and undoable. Fresh photos still default to legacy.
- A real action eyedropper is not yet enabled; neutral math alone is not that feature.

Sources of mathematical definitions/fixtures (not copied application code):
- W3C CSS Color4 CRD2026-10-20 conversion matrices:
  https://www.w3.org/TR/2026/CRD-css-color-4-20261020/#color-conversion-code
- Colour CIE D documented example and polynomial:
  https://colour.readthedocs.io/en/latest/_modules/colour/temperature/cie_d.html
- Exact community source pins, migration and acceptance obligations are in
  docs/development/white-balance-versioning-plan.md.

The bounded scalar ABI, state/preset/project v2 migration, export/batch and
picked-only activation are integrated. Independent Decimal combined-gain fixtures
and actual helper/production-stage tests complement the scalar tests. See
`docs/development/white-balance-actions.md` for exact-commit evidence and remaining
GUI/GPU/photographic acceptance.

## Bridge integration

The existing packaged math helper now has a bounded `white-balance-v1` scalar
command with strict action, argument-count and reply validation. Python recipe
installation prepares an immutable gain vector once; NumPy/Torch frame processing
consumes the vector without spawning a process. A 256-entry scalar cache is bounded.
Legacy calls remain on their unchanged numerical path. Picked-only vectors activate
the low-level preview stage and invalid preparation leaves its old state intact.

The initial bridge's independent Decimal oracle and actual helper/stage tests
passed on d6b401af in CI39738251607: 16 cases, no skips, in1.24s. Later integration
77add60a passed31 WB cases; user controls de5e8e2f passed40 WB cases in CI39744013157
(no skips,4.28s),176 frontend cases, native mailbox tests and builds. These are
synthetic/automated evidence, not desktop visual acceptance.
