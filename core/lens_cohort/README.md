# Original lens cohort core v2

AUTHORED / UNRUN. No compiler, tests, build, product imports, or image execution
were run. This is substantive renderer source, not established runtime support.
See `../../docs/lens-cohort/README.md` for scope, arithmetic and acceptance.

- `contract.rs` / `lens_cohort.h`: matching separate ABI2 layouts.
- `kernel.rs`: original v1 mathematical kernels and source-radius operation order.
- `fft.rs`: dependency-free original scalar f64 radix-2 FFT, bounded lines.
- `plan.rs`: whole-request work, memory, exact cohort and residual admission.
- `render.rs`: borrowed immutable job, exact residuals, ordered atomic tiles.
- `lib.rs`: span/nonoverlap-checked C boundary and contained Rust panics.
- `tests.rs`: independent direct comparator and real UNRUN fixtures.
- `build_lens_cohort.sh`: build-script source only; not invoked.

No external crate, generated library, downloader, model, or file I/O is included.
The original ABI1 directory was read, not edited. GPL-3.0-or-later applies.
