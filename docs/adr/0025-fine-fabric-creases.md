# Fine clothing crease shading

Use the fabric algorithm in Chris Cork's RapidRetouch revision
5e9d9c1d2770ff29d11a3879e5a90aad5887e028, AGPL-3.0-only. Preserve its attribution
and license in the engine package. This is brightness correction, not synthesis.

The scalar amount defaults to zero and belongs to the document recipe. Clothing
support is the confidence margin of the documented MediaPipe clothes class, not
inverse skin or a person silhouette. Erode support before measurement and set all
changes outside support to exactly zero. Semantic segmentation is imperfect;
conservative support prevents numerical spill, not confidently wrong predictions.

Measure log-brightness bands and crease lines once from the repaired source,
protecting texture, dense directional patterns, deep seams and clipped highlights.
Apply bounded gain in linear RGB before geometric deformation and global grade.
Source identity, repair version, mask identity and dimensions invalidate the cache.
The slider controls cached gain; it does not recompute image statistics each frame.

Unavailable clothing masks suspend rendering without replacing the stored amount.
Export must fail explicitly rather than omit an enabled unavailable layer. Export
remeasures at output dimensions once, then supplies the same field to all tiles.
Do not upscale the proxy's measured correction or independently measure tiles.

The initial scope is all confidently segmented clothes. No upper/lower separation,
per-person clothing assignment, coarse-fold removal, stain removal or regeneration
is claimed. No new model weights are required.

Development-only delivery: no build, runtime, type check, or regression campaign
was run for this package, per the user's development-first instruction.
