# Current-photo crown and side hair-volume UI

Status: authored source only. No product import/execution, typecheck, tests, build, inference, browser/UI run, image acceptance, installation, download, Git operation, or publication was performed by this UI worker. All fixtures in `ui/src/hairVolume/*.unrun.test.ts` are **AUTHORED / UNRUN**, not passing results.

## Preserved scope and intent

- Family: `lnx.hair_volume.v1`, distinct from full-head shrinking, dye/gloss, root/tip colour unification and generated hair.
- `control:PC-32472:2`: crown slider left lowers, right raises.
- `control:PC-32472:3`: side-volume slider left reduces, right increases; image-left and image-right can be linked or independent. Linking explicitly adopts the displayed left value, rather than silently averaging independent values.
- Direction requirements are preserved from the official guide `https://www.pixcakeai.com/guide/32472`, read by the coordinating task on 2026-10-25. That guide does not disclose these numerical ranges/defaults. UI −100…+100 maps to this implementation's original −1…+1 normalized range; neutral 0, geometry minima and displacement policy are local choices, not reference-product values.
- This is bounded current-photo, manually assisted 2D silhouette deformation using existing pixels. It is not density synthesis, automatic crown/ear detection, hidden-anatomy reconstruction, person-instance hair segmentation or an assertion of commercial pixel equivalence.

## Isolated integration surface

Only new `ui/src/hairVolume/` files and this document belong to this UI module. The parent owns App/people/native/engine integration.

Exports from `ui/src/hairVolume/index.ts`:

- `HairVolumePanel({port, engineAlive, onStartEngine, busy?, available?})`
- `useHairVolumePort(enabled, refresh, people)` returns `{port, state, check}` and mounts once at App lifetime.
- `createHairVolumePort(canUse, refresh, transport?)` accepts a dedicated submit/status transport for a future harness.
- `port.pending()`, `port.uncertain()`, `port.recover()` participate in the parent's existing serialization and uncertain-operation protection. Closing or unmounting the panel never owns canonical history and never cancels an issued operation.

Dedicated commands are `hair_volume` and `hair_volume_status`, not a people-patch fallback or a second history owner. Requests use protocol 1, operation ID, unique original request ID, exact selected-face `people_context`, action and payload. Actions: `context`, `preview`, `presented`, `commit`, `clear`. Result correlation requires exact event, protocol, family, request ID, action, document, full context and request-payload echo.

The source of truth for the UI DTOs is `ui/src/hairVolume/model.ts`. The host must provide genuine current source pixels and actual rendered review pixels; it must independently validate source proof, repair graph, retained analyses, people graph, entire edit state and engine capability at preview and again at commit. UI checks are not a substitute for this host authority.

## Source and observed support

1. Only the current selected, source-owned `FaceRef` in face scope is eligible. Group/person/all-people inheritance and synthetic/unresolved analysis do not authorize a nonzero operation.
2. Current source SHA must equal the selected current `FaceRef.asset_sha256`, including an actual derived source. A derived image must never use an old-original FaceRef. Source kind is descriptive only, not an identity exception.
3. The editor displays the complete actual source PNG, verifies delivered PNG SHA-256 and decoded dimensions, and maps both mouse and keyboard coordinates through normalized source coordinates. Pixel-index mapping uses `width−1` and `height−1`. Enlarging the thumbnail does not create new source detail.
4. No default crown, ear landmarks, expanded face box, donor mask or automatic patch is generated. Users independently mark outer transition bounds, internal plateau bounds, visible contour points and paired real-hair/clear-background probes for crown/image-left/image-right.
5. Three to 33 triples are required per active region. Tangential ordering is increasing X for crown and increasing Y for either side. The paired probe UI explicitly fixes only the tangent to the corresponding observed contour; the user chooses the normal coordinate. Crown hair is below the contour; image-left hair is to its right; image-right hair is to its left. Background is opposite.
6. Complete x/y profiles satisfy `a < b < c < d`. UI/source guards require an outer inset of at least one source pixel, fade margins at least four pixels and plateau extents at least two pixels. The contour spans at least half the tangential plateau; paired normal offsets are at least one source pixel. These are conservative local safety limits. The native geometry validator remains authoritative.
7. Users mark only actually visible ears, neck and other people. Canonical source-owned face protections are also supplied by the engine. Empty manual categories do not invent hidden anatomy and do not override engine protection. Merged hair evidence validates observations but is not per-person instance segmentation.
8. The compact boundary remains fixed: the crown's lower side and a side patch's inner side taper to zero. The clear outer background transitions continuously. Contact, clipping, occlusion, missing evidence, overlapping/protected unsafe support or inadequate transition reach must be rejected, not silently weakened.

## Independent consent, candidate and commit

- Recipe: `{version:1,crown:{version:1,amount},sides:{version:1,linked,left,right}}`. Linked sides must have identical values.
- Accepted draft geometry persists in the App-lifetime port. Incomplete local boundary numeric inputs and a first corner are explicitly canceled when the editor closes. Incomplete local patch arrays can persist but are never sent as valid support.
- The preview payload includes `recipe`, `regions`, `protection`, `confirmed:true` and separate `crown_confirmed`, `left_confirmed`, `right_confirmed`. Every active region requires its own complete geometry and consent. Inactive regions are sent as null even if an unfinished local draft exists. No different tool's review authorizes this operation.
- Changing one region clears that region's consent. Changing protection boxes clears all region consents plus visible-anatomy and whole-source review. Any accepted draft/recipe/consent edit removes the old candidate and image ACK.
- Before preview, the source image must have loaded and matched its hash and dimensions. Pending unaccepted coordinates disable consent/preview. Full-source ownership and visible-anatomy confirmations are distinct from each operation's contour confirmation.
- Preview returns the exact source, selected face, recipe, active regions, protection, frozen semantic evidence, support-asset digest and three actual full-frame PNGs: clean mixed-before, clean mixed-after and explanatory support overlay. The overlay never substitutes for clean comparisons.
- Each review image must decode to its declared dimensions, hash-match its delivered PNG bytes, be simultaneously at least 99% visible, be in the focused visible document, and survive two animation frames before the UI offers image approval.
- User review checkbox, host `presented` ACK and `commit` are separate steps. The ACK carries exact preview ID/token and all three actual image-byte digests. Commit requires this exact still-current ACK, not a generic checkbox or diagram. After the shared curve-edit barrier, source/context/candidate readiness is checked again.
- Applied edits go through the existing native canonical people state and unified history only. Keyboard undo/redo while this modal is open is intercepted so draft geometry cannot accidentally undo the underlying photograph.

## Unknown outcomes, navigation and recovery

- Lost admission, timeout, malformed terminal, mismatched receipt or unknown outcome preserves the original request ID and accepted draft. Recovery queries `hair_volume_status` for that ID; it never resends the write.
- Source/face/revision navigation makes the old draft stale and clears display/approval gates. It cannot adopt a new photo or clear the wrong person's operation.
- Native proof of an actual saved-project reopen is not proof that an old request succeeded, failed or was rolled back. Only an explicit user action may retire the old lock, preserving bounded original request/receipt/draft archives. Timeout, epoch change or navigation alone cannot retire it.
- Optional recovery UI lets the user explicitly choose and confirm abandoning the unsaved session and reopening a saved project. This does not overwrite the source/project or establish the unknown operation's outcome.
- A confirmed commit followed by refresh failure is still committed: the UI requests a display refresh, not another mutation.

## Authored verification matrix, all UNRUN

`model.unrun.test.ts` specifies version/range/equality checks, per-region consent, inactive partial exclusion, ordered paired probes, pixel minima, scale-independent click mapping, derived/current source identity, scope refusal, exact mixed-review fields, image ACK and query-only/reopen receipt correlation.

`wiring.unrun.test.ts` specifies dedicated transport/barrier hooks, no generic mask/history fallback, actual-source decoding/hash mapping, image visibility/focus/paint gates, separate controls and canonical-history keyboard protection.

Before calling this feature validated, the authorized integration owner must run typecheck and focused/full tests, plus real-source UI acceptance covering:

- Positive/negative/zero crown and side directions; asymmetric and linked sides; explicit link-value adoption; independent resets.
- Missing native core or hair evidence; wrong-source/derived-source mismatches; invalid geometry; protected face/ear/neck/other-person contact; cropped/occluded hair; insufficient background reach.
- Repeated clicks; source loading/error/hash mismatch; stale geometry; pixel entry; zoom/scroll; pointer cancel/blur; close/reopen and loss of incomplete coordinates.
- Real full mixed before/after against other retained edits; blank/cropped/corrupt/mismatched images; hidden tab/focus loss; stale ACK after recipe or repair changes.
- Navigation, delayed/out-of-order receipts, lost enqueue, query-only recovery, reopen evidence, archive budget refusal and successful commit with failed display refresh.

No runtime or photographic result from this matrix has been established by this module authoring pass.

## App integration source-only follow-up

The shared integration grant wires this module through `ui/src/hairVolume/useHairFamily.tsx`, a real bounded extraction of App-lifetime hair colour/unification/volume port ownership, their panel slots and activity descriptors. The existing colour/unification native ports remain the transport and receipt owners; no alternate history or duplicate queues are introduced. `familyAdmission.ts` queries sibling locks and deliberately ignores the target port's own reservation, including the second admission check after the curve-edit barrier.

`App.tsx` mounts this hook once and passes the actual slots into `RetouchPanel`. The panel renders the current-photo hair-volume workflow and suppresses only its now-covered crown/side placeholder leaves. Family pending/open/checking/preparing/refreshing/uncertain state protects global file/keyboard/compare paths, the event-capture guard, source crop, workspace navigation, peer panels and the ongoing-tool receipt/activity strip. A specific hair-volume allowlist keeps its own modal, close/recovery controls and original-request query accessible. Current source/document/load identity, people availability, engine protocol and queue state are checked independently of the target's own pending state.

The displayed third review PNG is explicitly labeled a source diagnostic with observed contour/protection boxes, not candidate segmentation or a rendered effect. The host may letterbox that complete source diagnostic to match the final before/after extent after crop or rotation. Protection caps agree with the core family: 2 exposed-ear boxes, 1 visible-neck box and 64 other-person boxes.

`integration.unrun.test.ts` adds authored, unrun cases for sibling-only reservation admission, every review-lock phase, bounded extraction/App line cap, actual panel/route mounting, source/context readiness, recovery activity, source-crop/global guards and the diagnostic label. All tests, typechecks, builds, product imports, runtime/UI execution and photographic acceptance remain UNRUN.
