# Eyelash source-wired slice, NOT runtime accepted

Initial isolated base: a904c5e8. Shared integration granted at
a5d205d08a574bca8efd672dd49897af468a0725 after brows. Shared source hooks below
are now wired; runtime, compiler and visual acceptance remain UNRUN.
No product module import/execution, tests, build, compiler, typecheck, inference,
download, installation, Git write, commit or push performed. Executable cases
are authored **UNRUN**. This file records source integration, not a runtime or visual completion claim.

## Requirement evidence

Official https://www.pixcakeai.com/guide/32471 read 2026-10-23, eyelash section
and makeup colour section: 14 effects, strength, left/right AND upper/lower
independence, recommended colours, eyedropper, RGB/HEX, six saved colours.
Manual baseline lines 541–545; AI mapping exact requirement IDs:

- LNX-REF-PC-32471-C-a985bd90b0: family, 14 effects, degree and four parts.
- LNX-REF-PC-32471-C-97176ce30b: recommended colours.
- LNX-REF-PC-32471-C-6188d1c325: verified frame eyedropper.
- LNX-REF-PC-32471-C-cc564a6b8e: RGB.
- LNX-REF-PC-32471-C-7379840b33: HEX.
- LNX-REF-PC-32471-C-18779c33fa: maximum six favourites.

Names, parameters, geometry, strength 0–1 normalization and thumbnails are ORIGINAL
local designs, not asserted competitor defaults, artwork or visual parity.
No competitor image/model/weights were downloaded or reused.

## Source-wired canonical integration map

1. `people_algorithms.py`: import eyelash_state as EYELASH and add OP specification.
   Canonical OP is `lnx.eyelash.v1`. Four independently persisted parts are
   `left_upper`, `left_lower`, `right_upper`, `right_lower`, each holding
   pattern/strength/colour. `/link_lr` and `/link_ud` give fourteen scalar leaves.
   No recipe is stored outside the canonical people graph.
2. `people_edit.py`: during scalar leaf validation ONLY, disable BOTH link_lr and
   link_ud for EYELASH; validate each complete staged recipe for every affected
   face after all patches and before publishing. UI emits all fourteen leaves
   in ONE patch receipt. One unsupported active part rejects the whole render.
3. `people_state.py` and `people_support_assets.py`: register separate kind
   `eyelash_visibility`; delegate record check, retain, resolve, raster and
   project validation to eyelash_support. Reuse SAME `_people_support` dictionary.
   Review rows contain `eyes` keyed by FOUR part names. Each value has separate
   `root_recipe` AND `extension_recipe`, plus visible/unoccluded/open_eye/
   ownership_confirmed. No eye-light or eyeliner review authorizes these zones.
4. `people_render_runtime.prepare`: add eyelash_assets from canonical support
   store, resolve eyelash_visibility explicitly, and call eyelash_people.prepare
   with verified analysis, frozen effect_source and state revision. Add facts.
   `people_effects.STAGES`, pipeline and source export must add `eyelash` after
   eyeliner and before common deformation; recovery targets must include eyelash.
   Render records are LocalEffect working-sRGB float32 deltas. Four parts are
   prepared before any result is returned; unavailable parts are not silently
   dropped. Review/root absence may omit unseen individual fibres, but rejects
   the active part if no complete fibre is supported. This is not hidden-lash
   reconstruction, profile completion or a narrow eyeliner-band rendering.
5. Host commands: `eyelash_reference` -> eyelash_host.reference;
   `eyelash_review` -> stage_review; `eyelash_palette` -> adapters.stage_palette.
   Existing checked envelope, receipt transaction, rollback/history and pending
   status own publishing. Extend Python and native IPC action allowlists.
   Host DTO must include `eyelash_host.report` as `eyelash`.
6. History/project/server document fields: include `_eyelash_library` using
   eyelash_project.capture/restore, default empty(), project key eyelash_library.
   Call validate_records on active/dormant/historical graph and palette, and
   eyelash_support.validate_project on current and historical support descriptors.
   Retain append-only support records for undo/redo. `_eyelash_reference` is a
   transient source/person-bound preview only, not durable applied state.
7. Presets: register eyelash_scope. Transport only canonical 14 leaves and
   catalogue version, not visibility, roots, extensions, source identity,
   recovery, palette, landmarks or someone else's support. Each batch target
   needs its own verified person and review. Use existing transfer preflight.
8. UI `people/model.ts`: EyelashView DTO and three action identifiers above.
   App imports useEyelashPicker/EyelashPanel and mounts them against PeopleOwner.
   Wire existing verified capture overlay presented/pick/failed methods, cancel
   all competing owners and block body/hair/tools during capture. The picker
   locks source/document/graph/target AND exact selected part when armed.
   No screenshot sampling, parallel palette owner or independent history stack.
9. `packaging/stage-engine.sh`: invokes packaging/build-eyelash.sh in authorized
   build, include eyelash_patterns.json, core source, licence and documentation.
   Scripts are authored UNRUN; missing native library refuses application.
   Native availability in host is file presence, not ABI/load/test proof.
10. Existing required runtime source list/project export support and palette
    keys must include eyelash equivalents wherever eyeliner is registered;
    do not mechanically transform eyeliner's left/right/linked schema.

## Geometry, visibility and safety limits

Measured 478-point MediaPipe landmarks bind roots to observed upper AND lower
lids. Outward direction follows actual eye centre, including image rotation.
Original deterministic quadratic fibres have varied length, density, taper,
curl and sweep; 14 profiles are numerically distinct, not visually accepted.
Root positions never extrapolate beyond observed corners. Each generated fibre
requires reviewed root ownership and a complete reviewed extension centreline,
densely checked at no more than half-pixel spacing; actual rendered coverage is
also multiplied by extension ownership and semantic occluder exclusions. This
preserves excluded pixels exactly. Root and extension masks are source-normalized
vectors rerasterized independently at preview/export size, never proxy masks
resized to source size. Root/extension fields and real semantic exclusions are
mandatory. Closed, clipped, tiny, degenerate, unseen or unsupported portions
refuse, rather than fabricate hidden geometry. Users must unlock and zero any
unavailable part. Manual ownership review is NOT automatic occlusion detection;
missed occluders in both user review and model evidence remain a visual risk.

No runtime fallback, compilation or installation occurs. Native ROI budget is
4 million pixels, at most 1,024 fibre segments. Current profiles use at most
640 segments per part. Budget errors reject rather than degrade silently.
All geometry thresholds, antialiasing, quality and performance need real-image
acceptance across skin tones, glasses, hair, occlusions, orientations and scales.
Thumbnails are illustrative and upper-lash-only, while the actual render supports
all four parts. Nothing here establishes production-quality or acceptance pass.

## Static authoring audit

Python files parsed using standard-library AST only; JSON decoded and exact
source bytes hashed. Product imports and all executable validation remain UNRUN.
Review `acceptance.json` and `SHA256.json`. Manifest excludes itself; coordinator
must retain its hash separately. The manifest now includes authorized shared wiring and excludes unrelated iris
files. Any subsequent source changes require a newly frozen manifest.

## Shared release audit

Shared ownership released after source wiring and static AST/JSON/hash review.
`people_state` already accepts source-owned named kinds through generic validated
descriptors; no second asset store or new schema owner was necessary. Existing
source-effect stage ordering is preserved with eyelash inserted after eyeliner,
before brow makeup and common deformation. Existing body v1–v6 code is unchanged;
App adds eyelash capture cancellation and busy gating to the existing owners.
The Viewer chooses the eyelash verified frame owner and uses the same presented/
pick/failed path as the other palette tools. All 28 acceptance cases and authored
Python/Rust tests remain UNRUN. Product imports were not used for source review.
