# Original neck core, ABI 1

24 f64 scalars in source pixels: center x, upper y, lower y; complete head/hair box x0/y0/x1/y1; transition box x0/y0/x1/y1; five negative-side contour half-widths; five positive-side contour half-widths; length, negative width, positive width in [-1,1]. Anatomical side selection is explicit upstream, not mirrored automatically.

Evaluate returns target minus inverse-source coordinates plus inverse determinant. State-independent ABI reports 1. Input contract: nonnull, correctly sized disjoint output/input buffers owned by adapter. Allocation is owned by the shared composition adapter, not Rust. Error 1 invalid input, 2 geometry/global contraction refused, 3 inverse/Jacobian/displacement refused. No unsafe aliasing pointers are exposed to UI.

Original C1 compact plateau and C1 contour fields, analytic gradients, global infinity-norm contraction upper bound, bounded fixed-point inverse, local determinant and displacement validation. No sampled field, face cutout, detached face transform, image sampling, model inference, dependencies or runtime compilation.

build.sh is a packaging artifact only. Compiler/build/native execution and every numerical/visual acceptance gate are UNRUN in this development phase.
