# Eye-bag review cancellation and request recovery

AUTHORED / UNRUN. This is workflow completion, not another image algorithm,
effect-recovery brush, automatic anatomical detector or photographic acceptance.
The original solver, protection core, source precision and review geometry remain
unchanged.

## Single owner and two different events

Only the existing people mailbox's retained original read proof can authorize
`cancel_eye_bag_read`. Eligible actions are source reference, native source image,
full candidate preview and review image retrieval. Confirmation is never eligible.
The native port writes `eye_bag_cancel` through the existing mutex-protected engine
input control lane, outside the normal serialized dispatcher wait. It neither
kills a process nor changes document state.

The command reader validates control metadata and sets a request-specific Event.
It does not decode images, mutate graphs or publish history. A bounded early-cancel
set covers cancellation that overtakes a queued read. Completion and cancellation
are ordered under the same lock. The actual image work remains on the established
serialized engine execution sequence.

Writing a cancellation request is not proof that work stopped. The original read
remains pending. Only after it has unwound does a canceled terminal carry
`eye_bag_cancelled:true`, `success:false`, `outcome_unknown:false`, its original
request identity and an error explanation. Canceled reads release unpublished
crop/review authority; they cannot publish a candidate. If the read finished
first, its original result remains completed, not retroactively canceled. The UI
discards a late result after its own cancel intent rather than reviving a preview.

## Safe points and limitations

Crop preparation, support rasterization, overlay conversion and canonical full
candidate rendering receive the same cancellation predicate. Existing decode/ICC,
PNG encoding and individual solver calls remain non-interruptible until they
return to a checkpoint. No maximum cancellation latency or instantaneous stop
is promised. Cancellation does not reduce solver context or source quality.

The existing one-line reader queue and native dispatcher retain their backpressure
rules. The control is not a general second command executor. Capacity overflow
fails closed without silently dropping cancellation.

## Query, recovery and reopen

The original request stays queryable. A narrowly validated later terminal may
reconcile an unknown read receipt only for that exact retained read-only eye-bag
binding and engine epoch. Known terminals and all writes remain immutable.

`recover_eye_bag_read` is query-only. It may release a local read wait after a
known settled read terminal, or after the original engine authority is unavailable.
A pending same-engine read cannot be released as stopped. A different engine
epoch proves loss of old authority, not that an old process was physically
interrupted. Missing/evicted proof is explicitly unavailable, not fabricated.
Confirmation, applied results and unknown writes cannot use this recovery path;
they retain the existing query/reload safety fences and are never resubmitted.

The existing app-lifetime people workflow retains a bounded same-owner draft
slot containing only recipe and whole-source brush vectors. Panel reopen does
not restore stale image tokens or acknowledgments: it requires a new source/crop
read and fresh per-eye ownership confirmation. Source, face, analysis, document
revision or scope changes invalidate reuse. This is not disk persistence across
application restart, nor a second graph/history store.

## Primary practices and licenses

- [Python Event objects](https://docs.python.org/3/library/threading.html#event-objects)
  provide a cooperative flag, not forced thread termination.
- [Rust Mutex](https://doc.rust-lang.org/std/sync/struct.Mutex.html)
  documents exclusive access. Existing engine input serialization and mailbox
  ownership are reused rather than introducing competing writers.

Documentation was consulted; no third-party code or weights were copied or
installed. New source keeps the repository's existing license. All native, UI,
request-race, history, reopen and numerical acceptance remains UNRUN.
