# Portrait protection UI/native integration — AUTHORED / UNRUN

No build, typecheck, tests, app launch, product imports, inference, install or download was performed. Only source text inspection/diff/whitespace checks. This is not visual or photographic acceptance.

## App.tsx hook (integrated; do not duplicate)

```tsx
import {PortraitProtectionControls} from './portraitProtection/PortraitProtectionControls';

<PortraitProtectionControls
  report={doc?.portrait_protection}
  disabled={!hasImage || busy || exporting || imageToolBusy || idBackgroundBusy || hairBusy || hairFamily.workflowBusy || creative.pending || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
  onChanged={refreshFromEngine}
/>
```

Mounted immediately before the real RetouchPanel in App.tsx; CoreStatusNotices wiring is preserved. The corresponding server handlers and state hooks are integrated. Existing precompute must produce actual single-face evidence before activation; enabling protection never initiates first analysis.

## Frozen wire

Request exact keys: `cmd:portrait_protection`, bounded `request_id`, `document_id`, canonical unsigned decimal-string `revision`, `controls`.

Controls exact keys: `enabled:boolean`, finite `strength:0..1`, `protect_identity_marks:boolean`, `analysis_enabled:boolean`, `overlay_visible:boolean`, integer `feather:0..256`, `protected_regions:[left,top,right,bottom][]` max64; finite normalized original-source coordinates, strictly positive extents. Feather is source pixels. Defaults false/0/true/false/false/0/[].

Terminal: `event:portrait_protection_result`, `protocol:1`, exact `original_request`, request_id, boolean success/outcome_unknown/requires_reload. Success only applied (+1 revision) or no_change (same revision), spec numerically exact controls. Failure only rejected/rolled_back (known) or unknown (both unknown/reload true), with error. Native-only `not_sent` has authority native-admission and cannot arrive from engine RX. Numeric strength 0 versus canonical 0.0 is intentionally equivalent after strict validation.

DocState report: controls/document_id/revision/active/analysis_available/reason. Availability is actual single measured face evidence or frozen same-source evidence, never capability alone. No classifier, scar/tattoo recognition, identity score, or multi-face fallback is advertised. Manual rectangles are editable source-normalized inputs, not falsely mapped current-canvas coordinates. Overlay switch describes engine preview-only overlay; no client-generated semantic mask is invented.

## Receipt and scope behavior

- Persist exact request before dispatch; reserve native ID before enqueue. ACK is never success. Native and UI retain uncertain pending across panel remounts. Invalid/unavailable session storage blocks new sends.
- Native epoch-bound dispatch rejects replacement-engine races. Engine validates original document/revision. UI never writes a result into the current doc; it refreshes canonical state only after exact terminal proof. Draft is keyed by canonical document/revision.
- Status only reads native retained mailbox, never retries edit. Missing mailbox is unknown, not evidence of non-delivery. Engine's separate retained receipt endpoint exists but is not dispatched by this UI.
- The portrait global mutation fence also survives workspace-open events until exact native abandonment, so an earlier buffered open cannot release it. Unknown can be explicitly abandoned only after native idle baseline followed by verified successful state-replacing project open, or known epoch replacement with idle queue. Attempted open, project create, old buffered open, elapsed time, and same-looking frame are not proof. Abandon does not label original outcome successful.
- Portrait reset generations now come only from bounded unique-key raw RX with strict project-open fields and optional boolean flags. Generic project-state handling cannot advance this generation. Malformed/duplicate command_done packets taint the current epoch's portrait idle proof for both same-epoch and replacement-epoch recovery; generic dispatcher behavior for other families is unchanged. Escaped event names are decoded for taint detection.
- Raw duplicate-key JSON rejected before receipt validation. First exact terminal wins. Wrong epoch/request/spec/revision/flags never clear fence. Other-family ID collisions cannot be settled or suppressed by this owner.

## Owned source manifest / protected neighbors

New: `ui/src/portraitProtection/model.ts`, `owner.ts`, `PortraitProtectionControls.tsx`; `ui/src-tauri/src/portrait_protection_api.rs`.

Narrow existing hooks:
- `ui/src/App.tsx`: real portrait controls mount only; existing notices/workflows preserved.
- `ui/src/native.ts`: optional portrait report. Separately authorized optional task delete receipt array.
- `ui/src-tauri/src/main.rs`: portrait module/three command registrations. Separately authorized task receipt field/init/retention/ready-clear/status.
- `ui/src-tauri/src/native_dispatch.rs`: only adds portrait_protection to existing epoch-bound allowlist; history/session/inspection/capture guards unchanged.
- `ui/src-tauri/src/engine.rs`: strict raw receipt observer, own-fence guard, generic-observer exclusion, no stale result canvas painting. Existing receiver families unchanged.
- `ui/src-tauri/src/project_recovery_fence.rs`: portrait joins guarded mutation/create-block/exact terminal/reset paths; own exact-pending helper. Existing history, flip, WB, hair, batch, preset, body, alias and other recovery behaviors preserved; portrait reset proof is now its own strict raw project_opened predicate (never create); existing families retain their old reset predicates.

Export-task delete-receipt plumbing is present in the preceding source baseline `53679e8` and is separate from this portrait feature. It retains at most128 raw outcome objects after task row deletion, clears on engine ready, and exposes them via status; no task mutation authority was added. Consumer verifies all causal scope fields.

## Acceptance matrix to execute only with later authorization

1. Missing/malformed report → no editor; pending recovery remains reachable. Empty/no-face/multi-face/derived source → activation blocked, neutral clear available.
2. Current canonical recipe shown separately from draft; cancel/reset does not invoke. Canonical document/revision switch resets draft, never moves rectangles between photos.
3. All seven controls roundtrip; integer/float strength JSON equivalents accepted. NaN/infinity/extra fields/wrong booleans/feather fraction/65 boxes/invalid extents fail closed.
4. Double click → one request; panel unmount/remount → same original request; ACK or timeout never success; exact status resolves without edit resend.
5. Applied must advance revision exactly once; no_change must not advance. Wrong request/spec/revision/epoch, malformed flags, duplicate JSON keys, fake native-admission engine packet cannot settle.
6. Different-family same ID retains its own fence and normal receipt. Unknown outcome blocks mutation/save/export; opening an actually confirmed project is recovery, creating a project is not.
7. Duplicate-key project_opened, malformed optional success/unknown/reload/readback flags, renamed receipt envelopes, and malformed/duplicate command_done cannot authorize abandonment. Buffered pre-operation project open and a query while in-flight do not arm recovery. Idle query then later verified open may enable explicit abandon; old result remains unknown.
8. Simulated frame delivery loss retains commit receipt and requests canonical refresh, never re-executes. Replacement workspace cannot receive result-to-doc writes.
9. Manual box boundaries and feather verified on actual source versus crop/flip; overlay verified preview-only and absent from export. This photographic/UI validation is UNRUN.
10. Export-task delete receipt survives row deletion and rejects wrong scope/token; latest128 bounded; new engine ready clears raw ledger. This adjacent acceptance case is UNRUN.
