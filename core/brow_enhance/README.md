# Original existing-brow enhancement

**AUTHORED / UNRUN.** Isolated GPL-3.0-or-later Rust source with no external crates,
new models, downloaded assets or copied third-party implementation. No imports,
compiler, build, test, typecheck or inference has been run for this change.

Exact reference: `LNX-REF-PC-32471-C-18765fa8ea` from the public
[PixCake makeup guide](https://www.pixcakeai.com/guide/32471): left weakens an
existing brow effect, right strengthens it; unlock permits independent sides.
The guide supplies behavior, not code or numerical coefficients.

This is not fourteen-pattern brow makeup, brow geometry, generic exposure,
added hair/stroke painting, reconstruction, a guided filter or an AI model.
It measures bounded existing dark contrast against real separate adjacent-
forehead support from the same source. Invalid or insufficient reference refuses
the whole requested side. Zero/bright/black/unsupported samples remain exact.

See [the numerical contract](../../docs/brow-enhance/NUMERICAL-CONTRACT.md) for
source ownership, original residual formula, conservative limits, failure
semantics, primary research, provenance and every remaining execution gate.
`brow_enhance.h` is the ABI contract. `tests.rs` is authored and entirely UNRUN.
`packaging/build-brow-enhance.sh` is authored only; do not execute without separate
authorization. It does not download dependencies or modify older kernels.
