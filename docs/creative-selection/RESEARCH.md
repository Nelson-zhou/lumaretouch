# Selection research and provenance

Research date: 2026-10-25 UTC. Primary public references were read via web lookup;
no source archive, binary, model, image asset or third-party implementation was
downloaded or copied into this module. Implementation and fixtures are original.
Status remains **AUTHORED / UNRUN**, not compatibility or licensing certification.

## Requirement anchors

The repository traceability IDs `ui:18` and `ui:19` both point to the
[official manual-tools guide](https://www.pixcakeai.com/guide/158252). Its regular
selection section describes rectangle/ellipse, feather, fixed ratio/fixed size,
inverse and four selection modes. Its free-selection section describes a lasso
that closes on release and a selection brush with add/subtract, diameter,
hardness and opacity. This work implements a numerical contract for those
behaviors, not a copy of the proprietary product's code, visual assets or kernel.

The linked [creative workflow guide](https://www.pixcakeai.com/guide/127932),
traceability `workflow:127932`, places those tools alongside a multilayer canvas
and layer masks. That motivates a separate selected-layer projection/application
stage; it does not justify marking the whole workflow complete. The page also
describes locked targets and history, so target/revision checks and transactional
history are host responsibilities, not numerical-core side effects.

## Mature behavior references

- [GIMP 3 selection tools](https://docs.gimp.org/3.0/en/gimp-tools-selection.html):
  reference for selection-tool families and replace/add/subtract/intersect modes.
  We use the behavioral concept; no GIMP implementation or documentation wording
  is embedded in the core.
- [GIMP feather](https://docs.gimp.org/3.0/en/gimp-selection-feather.html): reference
  for soft coverage transitions and the importance of explicitly deciding
  image-border behavior. Our v1 uses zero extension and a specified finite box,
  without claiming GIMP kernel or optional outside-image-continuation parity.
- [Cairo paths](https://www.cairographics.org/manual/cairo-Paths.html): reference
  for path closure, flattened geometry and explicit path lifecycle boundaries.
  No Cairo API, rasterizer, tessellator or code is linked or vendored. Active-edge
  scanlines and capsule distance coverage here are independently authored.

The public guides do not define proprietary floating-point operators, antialias
quadrature, brush falloff, feather support, ABI, tile ordering or cancellation.
Those details in this implementation are explicit original engineering choices,
not claims about undisclosed source algorithms.

## License distinctions

- The [GIMP official FAQ](https://www.gimp.org/docs/userfaq.html) identifies GIMP
  software as GPL v3 or later. The
  [program license text](https://www.gimp.org/about/COPYING) is GPL version 3.
  GIMP is not MIT/BSD and is not a dependency of this module.
- The GIMP manual separately includes a
  [GNU Free Documentation License 1.2 appendix](https://docs.gimp.org/3.0/en/legal.html).
  Documentation licensing must not be confused with the program's GPL license;
  this module links and paraphrases narrowly rather than copying manual text.
- The [Cairo official project page](https://www.cairographics.org/) states the
  choice of LGPL version 2.1 or MPL version 1.1. Do not relabel it as MIT, MPL 2.0
  or an unrestricted public-domain rasterizer. An attempted `/license/` page was
  unavailable, so this statement is based on the verified official homepage.
  A future dependency/source import would require checking its actual files and
  notices; auxiliary tests/tools can have different licenses from the library.
- New Rust, header and test files use `GPL-3.0-or-later`, consistent with nearby
  original modules. This is an authored project module license declaration, not
  a claim that borrowed third-party code has been relicensed. The crate has no
  external dependencies and no copied third-party source.

## Decisions and honest gaps

Original Rust was selected to isolate the native ABI, avoid a new large graphics
dependency and make source-grid coverage, bounded allocations and deterministic
tile semantics inspectable. This does not by itself prove numerical correctness,
license compliance for the entire repository, competitive performance or visual
equivalence. Those need execution and review under separate authorization.

No official screenshots have been reproduced. No official-product sessions,
native visual comparisons, throughput measurements, builds or tests were run.
