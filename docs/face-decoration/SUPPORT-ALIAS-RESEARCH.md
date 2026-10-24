# Shared-source visibility painting: transaction rationale

Requirement remains LNX-REF-PC-32471-C-dd14134407; this is a workflow completion,
not a new material, renderer or automatic segmentation algorithm. Baseline
45eba231affdb5248c5a396ad8854da6935172ec. Source-only, acceptance UNRUN.

Primary practice and licence references are recorded in MULTIOWNER-RESEARCH.md:
the official decoration guide establishes the existing material/strength scope;
darktable's copy/paste and snapshots manuals motivate keeping mask ownership
separate from portable scalar intent and reviewing complete image states. No
upstream source, prose, artwork or masks are copied, and no dependency is added.
Re-read 2026-10-24: [copy/paste](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/copy-paste/)
excludes automatically copied mask-management data; [snapshots](https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/darkroom/snapshots/)
labels stored/current images and distinguishes snapshots taken from another image.
These are design practices, not imported darktable behavior or file compatibility.

The existing source canvas paints normalized geometry against authenticated
source pixels. A shared-source visibility change differs from a scalar edit:
the candidate graph references a new immutable support record. Preview must
stage both graph and bank without calling the live single-photo stage_review.
Each affected logical document retains its own crop, colour, repair and complete
render state. Coverage includes every enabled active before/candidate face.

The existing recovery-alias transaction provides a local architectural pattern,
not a target-name substitution. Decoration visibility uses its own checked
record and resolver; recovery-vector resolution is not interchangeable. The new
history marker and private authority must admit only the selected visibility
pointer, never pattern/strength, other support, another face or associations.

## Exact bank invariant

The canonical bank is append-only. Review freezes the live prior bank and the
staged candidate bank. Publication may append only the exact selected immutable
visibility record and must not alter retained bytes. History retains selected
before/after records and all referenced dependency proofs. Undo restores the
selected pointer while retaining immutable records needed by other history;
it does not claim to delete all later or unrelated bank bytes. Conflicting
record contents, missing referenced records or changed dependencies invalidate
replay. This invariant is deliberate, not a historical whole-bank snapshot.

A neutral before state may have no old visibility pointer. An active before
state with invalid support cannot be fabricated merely to permit an edit.
Identical canonical support is a no-op, not a revision-only transaction.
Every member's actual before and after image must be served and acknowledged.
Float-bearing draft/review hashes are opaque engine identities; exact original
request echo binds the draft, and cross-language ACK hashing covers only its
integer/string fields.
