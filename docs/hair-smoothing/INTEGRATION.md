# Reachable integration and receipt ownership — UNRUN

## One source stage, one graph, one receipt owner

`ui/src/components/RetouchPanel.tsx` binds only family `PC-32472`, exact leaf
`头发柔顺`; neighboring `头发柔顺/发丝调整` still falls through to the incomplete
control. `App.tsx` instantiates the stable port at application lifetime alongside
`usePeopleWorkflow`, with existing hair-family mutual exclusion. The panel owns
editing drafts, never another pending-request ledger or people graph.

The five independently tagged actions are `hair_smoothing_reference`, `_preview`,
`_crop`, `_confirm`, `_detach`. The existing people envelope supplies exact
request/document/epoch/revisions/FaceRef. Application-lifetime review guard,
`hair_smoothing_people.rs`, `people_api`, `receipt_host` and canonical engine host
bind source, original request, image hashes and post-state. A nonzero parameter
patch cannot bypass independent review. No colour/volume/neck consent is reused.

The new `hair_smoothing` source stage is after `hair_unification` and before
`eye_light`; common face/body geometry is sampled once afterward. All engine
preview, candidate and export paths forward the same support bank, original
source resolver and retained hair evidence. Full candidate proof carries exact
`hair_smoothing_measurements` and denies display-projected review authority.

## Persistence and transfer

Sparse amount lives in the existing people graph; support vectors/proofs live in
its existing immutable support bank. Existing project/undo/redo/private virtual
copy ownership retains those references. Historical validation resolves the
nearest retained banks without rebinding old evidence to today's live census.
Live rendering checks the actual current retained-face/ownership proof. Absent
neutral smoothing defaults are excluded from old source-context hashes; source
pixels and old neutral operations are not rewritten. Empty neck/hair measurement
diagnostics and unused private repair-input attributes are omitted, preserving
strict neutral full-render and ExportSpec schemas. Active review still requires
all exact active source FaceRefs and the requested measurement key. Retained
manual smoothing support is admitted by the existing hair-only replay path on
reopen/export; missing evidence refuses rather than invoking a producer.

Generic nonzero preset/cohort/shared-owner/alias activation and generic face
recovery refuse. Current-face independent zero/detach does not need decoding,
semantic model availability or a numerical core. Detached immutable bytes remain
available to canonical history; no fourth ledger is introduced.

## Terminal safety

Known terminal receipts require their exact retained request/epoch, source and
image proof. Unbound malformed same-ID echoes cannot poison this operation's
pending request. Unknown remains query-only across panels; no retry creates a new
write. Exact late read terminals may reconcile the original read, never grant
write replay. Confirm uses one private publication permit and exact prewrite
source/graph/support fences. An uncertain mutation remains an autosave barrier;
`project_create` does not clear it because creation retains live documents.
There is no timeout unlock. A proven prewrite refusal with an unchanged graph
fence can be known failure. The inherited people rollback advances fences and
does not supply exact restored-frame/history proof: such publication failures
remain unknown, even if a compensating graph write succeeded. Recovery requires
a verified workspace reopen, not a guessed rollback or resubmission.

Application-lifetime retirement uses the existing native receipt row, not merely
a changed document epoch. After native admission finishes, a query observes an
unresolved request with an idle FIFO queue **before** sampling the open counter.
Only a later verified replacing open, or a known different live engine epoch,
plus an idle queue can return exact original-request abandonment proof. An
earlier buffered open only establishes the baseline; creation/navigation/death/
timeout and a status stamp alone never release it. The stamp only triggers an
original-request query. Both native and UI keep the old outcome unknown, block
late callbacks from reviving it, and leave other People pending owners untouched.
The smoothing native recovery fence is retired by that exact proof, not a raw
open event. If needed, query after the queue stops, reopen the confirmed project,
then query again; never resubmit the old write.

Receipt and recovery-fence checks are symmetric: a tagged smoothing zero-patch
terminal cannot settle an ordinary patch with a reused ID/action/document, and
an ordinary terminal cannot settle a retained smoothing request.

Three bounded PNG displays have an operation-specific 18MiB result cap and a
32MiB cap in the existing receipt ledger; other families keep their prior caps.
Older known images can be released/evicted, not repurposed for another candidate.
Native-core availability is matching installed ABI/symbol readiness only, not
photographic or runtime acceptance. Packaging stages actual Rust sources, header,
license/notice and the build artifact; there is no runtime compile or fallback.
