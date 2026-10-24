# Original facial structure kernel

AUTHORED / UNRUN. Zero external crates. GPL-3.0-or-later.

Produces a bounded source-owned log-gain field from two support-normalized log-luminance means at measured face scales. Bright and dark broad structure have separate nonnegative controls. It does not calculate gloss/specular color residuals, blur the output texture, move face coordinates, reconstruct 3D or synthesize a light source.

The canonical host authenticates source and review ownership; native buffers cannot establish identity. Full source-window measurement happens once. Output is private until success, cancellation/errors leave caller output unchanged. Common linear-RGB composition is in facial_sculpt_composition.py and never runs the estimator again on an export tile.

Native test fixtures are in facial_sculpt_tests.rs; none were compiled or run. See ../../docs/facial-sculpt for exact requirement provenance, license review, shared integration contract and unresolved acceptance gates.
