# Batch undo scope correction (candidate, unverified)

The existing batch undo conflict check compares only synchronized module parameters,
but restoration previously replayed the entire old document snapshot. That could
erase later changes in unrelated modules despite passing the conflict check.

The correction applies the recorded before-parameters for the synchronized modules
into the current state, then replays/parks that merged state. Tests cover parked and
live targets plus the real shared exposure tuple: undoing synchronized EV must keep
later white-balance/tone edits. Root static review found no new nested-container
aliasing in the current scope writers. Execution is pending CI/Qoder.

Existing contracts remain: changed synchronized parameters are conflicts; skin and
blemish share strength, so they are not independently restorable. WB reference-K
is outside the transferable WB parameter scope and remains current. This restores
synchronized parameters, not a guarantee of historical visual WB under a changed
reference. Stable target identities and frozen preflight are separate unfinished
work, documented in frozen-batch-preflight-plan.md.
