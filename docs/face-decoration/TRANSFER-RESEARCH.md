# Complete face-decoration transfer review

Baseline: `9d2d97fbbe5ef879a43e9bb29be5a9c5d3e56038`.
Source implementation only; all runtime and photographic acceptance is UNRUN.

This closes workflow gaps of `LNX-REF-PC-32471-C-dd14134407`, not a new
decoration algorithm or an additional eight feature counts. The existing
original GPL-3.0-or-later materials and Rust numerical kernel remain unchanged.

## Primary practice checked on 2026-10-24

The [official makeup guide](https://www.pixcakeai.com/guide/32471) still specifies
five freckle and three mole-style materials with strength. It does not supply
artwork licences or a transferable visibility/occlusion guarantee. No commercial
patterns, example photographs or vendor code are imported.

The [darktable copy/paste manual](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/copy-paste/)
distinguishes selective parameter transfer from replacement of a destination's
history, and excludes unsafe internal mask-management information from ordinary
copy. This informs the separation of portable scalar intent from target-owned
support. Lumaretouch does not implement darktable's history semantics verbatim.

The [darktable snapshot manual](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/darkroom/snapshots/)
uses labelled stored-state/current-state comparisons. Here both images must
represent complete canonical target render states, not a decoration-only overlay
on a possibly different thumbnail. The exact target source, repair, graph,
support and output geometry belong to the frozen evidence.

The [upstream documentation licence](https://github.com/darktable-org/dtdocs/blob/master/LICENSE)
contains GPL version 3. These are design-practice references only: no upstream
source, prose, screenshots, masks or assets are copied. No dependency, model,
weight or third-party licence payload is added.

## Intended bounded architecture

- One-photo presets stage the exact complete portrait plan and non-portrait
  state, render both states through the canonical full-source pipeline, and
  publish only that frozen plan after image acknowledgment.
- Ordinary batch targets retain their own FaceRef, visibility review, measured
  skin, recovery and repair. Only versioned pattern and strength transfer.
- Existing active decorations must also be represented when another selected
  effect changes the complete image. Coverage cannot stop at the mapped face
  while an enabled unmapped face contributes to the rendered result.
- Display PNGs are bounded session evidence, paged by immutable proof. They are
  not masks, master pixels, project-history bitmap copies or full-resolution
  inspection. Failed reads do not constitute image acknowledgment.
- Existing history/ledger transactions own commit and rollback. Unknown writes
  remain query-only. Expired plans, changed source or changed support require
  a new review, never a blind retry or recomputation under an old acknowledgment.
- Shared-source aliases, persistent cohorts and incompatible dedicated review
  owners remain explicit boundaries unless their complete affected-image proof
  is actually implemented. Manual support remains manual, not automatic AI.

The implementation contract and UNRUN cases record the final admitted routes;
this research note is not evidence that those routes have passed acceptance.
