# Remaining functional groups: sampled evidence, not a completion percentage

Baseline: original product manual text and AI development package. This is a
focused source-backed sample audit, not a claim that every requirement was audited.
Overlapping specification leaves are not a meaningful completion denominator.

1. Action eyedroppers. Manual paragraphs around lines 510/545/579/607 and
   PC-32455 specify white-balance, levels black/white, curves and HSL pickers.
   The identified proxy RGB/Lab reader is read-only; it does not implement these
   actions. Next requires source-stage-correct sample-to-edit transactions with
   document/revision fencing, not simply applying output RGB to input controls.
2. Parametric curves. The mapping includes PC-32455 曲线/参数曲线. Existing
   master/R/G/B and linear-Y point curves are implemented and remain intact.
   Parametric tone regions need a separate documented recipe/control contract.
3. Full mask stack. Manual lines 612–616 require selectors, linear/radial
   gradients, color/luminance ranges, edge controls, add/subtract and mask-list
   visibility/edit/delete plus synchronization rules. Current all/skin/brush
   grading and one brush-mask clear command are not this stack. Persisted named
   entries, compositing and undo/save/export parity are prerequisites.
4. Independent patch and clone. Manual lines 629–633 distinguish source/target
   patch and sampled clone from spot heal. RetouchPanel deliberately leaves patch
   and clone disabled; repairToolHonesty guards against relabeling heal. Add real
   source-anchor/offset operations, not aliases.
5. Portrait subfamilies. Manual lines 501–566 and 587–591 include independent
   face/eye/teeth detail, makeup, hair, body, hands/feet and clothing controls.
   Existing four deformation kinds and sclera/iris/teeth enhancement are real,
   but do not fulfill all these families. Unwired spec headings are not features.
6. Frozen batch preflight. AI acceptance BATCH-001 requires source-version snapshot;
   BATCH-002 requires changed targets after preflight to be skipped/reconfirmed.
   Current preflight emits and returns; commit captures current data again with
   no token. Existing post-commit undo conflict checking is implemented, not absent.
   Add immutable preflight records, source snapshot and target identity/version
   checks, including document reorder and later editing.

Known functional defect: ordinary crop preview aspect remains incorrect because
fixed proxy raster dimensions are treated as presentation dimensions. See
frame-presentation-plan.md. Frozen colour capture and full-source inspection have
separate correct geometry paths; they do not repair ordinary viewing.

Deep real-machine visual/performance testing remains deferred, not removed. Basic
compile and deterministic functional checks remain mandatory for each change.
