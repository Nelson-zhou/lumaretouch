# 下庭 UI: authored, not runtime accepted

Status: AUTHORED / UNRUN. No code imports, tests, builds, type checks, application runs, inference, downloads, or photo acceptance were performed for these changes. Source inspection and source editing are not runtime verification.

## Exact requirement and scope

- AI development mapping supplied by the coordinating task: `LNX-REF-PC-32466-C-1ae8316994`, `PC-32466`, `脸型/下庭`.
- The repository's frozen `ui/src/spec/refine.json` lists 下庭 separately from 中庭, 人中, 下巴长短, 尖下巴, 收下巴, 小脸 and 短脸. Its range, default, step and left/right-unlock fields are unspecified. `docs/development/handbook-traceability.json` still marks this exact leaf `pending_independent_verification`; this UI work does not change that status.
- Frozen source: https://www.pixcakeai.com/guide/32466 . Current semantic source, verified by the coordinating task: https://wiki.pixcakeai.com/guide/9405.html . Positive lengthens the lower third; negative shortens it.
- Exact UI route: `PC-32466|脸型/下庭` → `lower_face.amount`. Distinct operation: `lnx.lower_face.v1`, recipe `{version: 1, amount: 0}`, finite signed `amount` in `[-1, 1]`. Display `[-100, 100]` is a product-local range, not a handbook-prescribed quantity or quality claim.
- Existing 小脸, 瘦脸, bilateral contour, feature routes and historical presets remain untouched. Unmanaged documents show an explicit unavailable panel with no whole-face, old small-chin, chin-length or short-face fallback.

## Geometry language and boundaries

The control describes the source-owned, measured 478-point nose-base and chin landmarks as proxies, not clinical anatomical measurements or proof of visibility. The whole below-nose interior, including lips, participates in a smooth nonuniform vertical warp in the head frame. This is not uniform scaling of every lower-face position. The new map has no horizontal displacement and fixes the upper region; that does not promise the final composite preserves original upper-face points because prior edits may move those points into the new map's transition.

The original, uncomposed nose-base/chin proxy endpoint interval in the lateral core changes by `1 + 0.08 * amount`, from `0.92` to `1.08`. This display is a parameter-derived reference, not measured rendered geometry, a uniform local scale, or a photo acceptance result. Neighboring neck and background in the feather also move. This feature is not whole-face size, chin-only small_chin, ear-based short-face, AI/3D reconstruction, or new segmentation. Engine checks, not UI guesses, decide actual geometry suitability and coexistence.

## Ownership and intended behavior

The existing people owner is the only command, queue, receipt, undo, and replay authority. This control sends only `/amount` via `people.patch`. Reading requires the exact selected face, document/source identity, analysis revision, state revision and association revision. Unknown, stale and conflicted reads remain unknown. The selected effective value and provenance are distinct from the editing target's explicit value; shared all-people, group and person targets without an explicit amount start blank and require a deliberate new choice rather than copying a selected face's inherited amount.

Source/target/revision/selection keys discard obsolete callbacks and drafts. Owner identity, pending, uncertain, disabled-owner, and competing editor queue fences guard writes. Neutral recovery needs current source and valid target ownership but not a working native core, readable effective value, or verified anatomy. It writes exactly one explicit zero; it neither unsets inheritance nor changes any other operation. Uncertain requests are queried through the original owner and never resent here. Original engine refusal text and owner errors remain visible; no unsupported compatibility promise or bypass is added.

## Authored verification, all UNRUN

- `model.unrun.test.ts`: strict recipe/finite signed range; positive/negative endpoint direction; exact IDs; dedicated capability; authoritative selected effective value/provenance vs target explicit values; shared blank choice; missing/stale/conflicted/disabled/synthetic reads; source/ref/revision/target/owner fences; neutral reset; isolated patch; nonmutation and absence of guessed coexistence restrictions.
- `wiring.unrun.test.ts`: exact route and all old routes/presets retained; unmanaged refusal; dedicated capability fields; existing single people owner and competing editor fences; no fake zero or borrowed shared baseline; stale callback/owner/repeated click guards; query-only uncertain recovery; neutral action independent of anatomy/native; visible proxy, nonuniform warp, composition and quality limits.

Still unverified: TypeScript compatibility, compilation, every authored test assertion, mounted React interactions, native bridge availability, the actual source-owned geometry, lips and chin motion, both amount signs, yaw/occlusion/clipping refusals, rapid photo/face/scope switching, shared-scope engine outcomes, old-geometry composition (including points entering the transition), neighboring faces, neck/background quality, zero/undo/redo/history/replay, preview/export parity, full-resolution real photographs, packaging, and complete handbook/development-pack acceptance. Source-contract fixtures do not substitute for runtime tests or photo QA. This leaf does not complete the 面部重塑 family.
