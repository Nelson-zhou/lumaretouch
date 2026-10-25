# Light-glow App binding

Status: AUTHORED / UNRUN. This note describes the small App integration boundary.
No build, typecheck, test, application execution, inference, model download or
rendering was performed for this binding. Native availability and production
correctness are not implied by the source files being present.

## Owned adapter

`ui/src/lightGlow/useGlowWorkspaceBinding.ts` calls the existing `useLightGlow`
owner with one App-lifetime `createLightGlowNativePort` instance. Its committed
engine-key ref tracks the real App engine identity without replacing the port.
It adds pending-curve settlement and live-context preflight before a new current
acquisition, preview or apply. The current request ID, capture acceptance,
candidate, write command, receipt and uncertain-outcome ownership remain in the
existing owner/controller/native port. There is no second source store or request
ledger.

Preview/apply require the accepted source's engine, App scope, native session,
source owner and load ID to match. An App revision is only an invalidation key;
it is never converted into a canonical native document revision. Cancel can
release its original same-engine session after a photo/workspace switch, but
cannot send that session to a replacement engine. Pending reads are not used as
an admission check inside `beforeRead`, because the port has already reserved
the very read being checked.

Opening/mounting does not acquire or render anything. Hiding only unmounts the
presentation; the App hook remains mounted and keeps observing original work.
The existing `onChanged` callback receives the actual terminal receipt and exact
command. The wrapper does not catch refresh failure or fabricate refresh success.

## Minimal shared integration

The integrating owner, not this isolated adapter, edits App and shared files.

1. Add direct App imports:

   ```ts
   import {useGlowWorkspaceBinding} from './lightGlow/useGlowWorkspaceBinding';
   import {LightGlowWorkspaceHost} from './lightGlow/LightGlowWorkspaceHost';
   import {GLOW_PROTOCOL, validGlowCapability} from './lightGlow/model';
   ```

2. Extend `EngineStatus.ready_caps` in `ui/src/native.ts` with optional wire
   fields, not hard-coded runtime capabilities:

   ```ts
   light_glow_protocol?: number;
   light_glow_capability?: unknown;
   ```

   Keep external capability JSON `unknown` until `validGlowCapability` checks
   exact protocol/operation/ABI/math/schema. Neither protocol presence nor a
   packaged filename alone makes the feature available. Missing/unavailable
   native support must remain unavailable; do not install a mock port.

3. Add ordinary App visibility state next to the lens/expression panels:

   ```ts
   const [glowOpen, setGlowOpen] = useState(false);
   ```

4. After the existing lens hook, call the binding unconditionally:

   ```ts
   const glowCapability = caps?.light_glow_capability;
   const glow = useGlowWorkspaceBinding({
     sourceUid: doc?.source_uid ?? '',
     loadId: doc?.document_id ?? '',
     engineKey: String(pid ?? ''),
     hostRevision: status?.doc_rev ?? -1,
     active: workspace === 'creative',
     available: !!status?.engine_alive && hasImage
       && status.image?.load_id === doc?.document_id
       && caps?.light_glow_protocol === GLOW_PROTOCOL
       && validGlowCapability(glowCapability) && glowCapability.status === 'available',
     externalBusy: imageToolBusy || idBackgroundBusy || creative.pending
       || expression.busy || expressionOpen || lens.busy || lensOpen
       || colorSampler.active || sampleLibrary.open,
     queueBusy: !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending,
   }, refreshFromEngine);
   armBusyRef.current = armBusyRef.current || glow.busy;
   ```

   `refreshFromEngine` already requests authoritative session state and refreshes
   native status. Preserve that read-only refresh. Do not select or update the
   original source optimistically; an applied receipt identifies the distinct
   new document. A refresh-only retry must never reissue apply.

5. Mount the host unconditionally next to `LensWorkspaceHost`, not inside the
   creative workspace condition or keyed by the selected photo:

   ```tsx
   <LightGlowWorkspaceHost owner={glow} open={glowOpen}
     onOpen={() => setGlowOpen(true)} onClose={() => setGlowOpen(false)}/>
   ```

6. Connect only creative tool ID `211524` to `setGlowOpen(true)`. Keep its
   unavailable reason honest. Do not alias lens blur `165438`, silently route
   another light tool here, or auto-acquire when navigation opens the panel.

7. Extend the existing App cross-tool event guard with the glow owner boundary:

   ```ts
   if ((glow.busy || glowOpen) && event.target instanceof Element
       && !event.target.closest('[data-light-glow-workflow]')) {
     event.preventDefault(); event.stopPropagation(); return;
   }
   ```

   Keep the glow boundary's close/reopen/status controls reachable. Central
   navigation admission and keyboard/native mutation guards must include
   `glow.busy`; opening glow must be rejected while another modal owns the UI,
   and vice versa. Do not add `glow.busy`, `glowOpen`, or `queueBusy` to glow's own
   `externalBusy`: that would invalidate its own work. Do not remount the binding
   to break an unresolved request. Native global admission remains authoritative.

## Static review and remaining acceptance

This binding does not change numerical recipes, preset values, rendering math,
image verification, native request envelopes, return mode or cancellation proof.
Only native-backed `new_image` return is supported; it is not an editable glow
layer and does not implement replacement of the original photograph.

Acceptance remains unrun: repeated acquisition clicks while settling a curve;
source/load/revision/engine changes during each await; stale same-engine session
cancellation; replacement-engine rejection; queue updates during the module's
own preview; hiding/reopening with pending or unknown work; correct new-document
refresh and refresh failure; unavailable/malformed native capability; and
cross-tool pointer, keyboard, import, workspace and export admission.
