# Shared-source and persistent-member decoration review

Baseline `b90f103abcf4c8ec7a5eb5032b228a1f1395db11`. Requirement remains
`LNX-REF-PC-32471-C-dd14134407`; no new algorithm or material count.
Source implementation only, all runtime and photographic acceptance UNRUN.

## Primary practice and licence

The [official decoration guide](https://www.pixcakeai.com/guide/32471), checked
2026-10-24, defines five freckle and three mole-style materials with strength.
Its proprietary materials are not imported. The eight existing original GPL
materials and Rust numerical method remain unchanged in this workflow slice.

The [darktable copy/paste manual](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/copy-paste/)
distinguishes parameter selection from replacement of target history, and treats
mask-management data as unsafe for ordinary copying. The [snapshot manual](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/darkroom/snapshots/)
distinguishes a stored image state from the current edit, including when viewing
another image. These practices inform explicit target ownership and visibly
labelled complete-image comparison, not compatibility with darktable files.

The upstream [documentation licence](https://github.com/darktable-org/dtdocs/blob/master/LICENSE)
contains GPL version 3. No upstream source, prose, screenshots, artwork or masks
are copied. No new model, dependency or third-party licence payload is added.

## Distinct ownership problems

A persistent association transmits scalar intent among explicitly confirmed
people. Its source and every member must retain their own observed anatomy,
visibility review, repair and local photograph state. A source photograph is
also a reviewed member, not an invisible donor exempt from image confirmation.
Retained active decoration on other enabled faces belongs to full-image proof.

A source-identical alias shares a canonical portrait graph. A scalar edit can
therefore affect multiple logical documents despite only one being visible.
Each affected document still has independent crop, colour and repair state.
Review must enumerate the complete affected set and render those exact local
states against the same proposed graph before publishing it once.

Independent virtual-copy/import owners must not be merged merely because source
bytes match. Unavailable siblings or dormant source-bearing histories cannot be
silently discarded to manufacture a complete affected set. Newly added siblings
invalidate a previously reviewed set.

## Bounded scope selected

Persistent association scalar edits and direct alias scalar pattern/strength
edits are the current implementation goals. Existing immutable visibility support
must already be valid for each involved source and observed face. Alias support
painting changes support pointers/bank history, unlike a scalar-only ledger
entry. It remains a separate missing path unless a genuine immutable support
transaction and exact before/after evidence are implemented. A scalar review is
not permission to mutate paint or to copy one member's mask to another.

Authority for an otherwise guarded alias transition must be private, typed and
bound to the exact before/candidate graph, source owner and complete member set.
It cannot be a request boolean or a broad exception to normal edit guards.
Canonical scoped history remains the only publication/undo owner.

Final admitted routes and remaining limits are recorded in the implementation
contract; this note does not claim completed functionality or tested acceptance.
