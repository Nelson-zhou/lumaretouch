// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import {CreativeSelectionController, type CreativeSelectionWorkspaceContext} from './controller';
import {selectionKey, type CreativeSelectionPort, type SelectionApplyRequest, type SelectionReply} from './model';

/** Mount once in App, outside the conditional creative panel. One stable adapter owns all original requests. */
export function useCreativeSelection(context: CreativeSelectionWorkspaceContext, port: CreativeSelectionPort,
  onApplied: (reply: SelectionReply, request: SelectionApplyRequest) => Promise<void> | void) {
  const changed = useRef(onApplied); changed.current = onApplied;
  const controller = useMemo(() => new CreativeSelectionController(port, context, {onApplied: (reply, request) => changed.current(reply, request)}), []);
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const identity = selectionKey([context.scope, context.binding]);
  useLayoutEffect(() => {controller.updateContext(context);}, [controller, identity, context.active, context.available, context.busy]);
  useLayoutEffect(() => {if (port !== controller.port) controller.adapterChanged();}, [controller, port]);
  const pending = controller.unresolved();
  useEffect(() => {
    if (!pending) return;
    // Observe the same request only. No automatic capture, rendering, replay or history operation.
    const timer = setInterval(() => {void controller.check();}, 1200); return () => clearInterval(timer);
  }, [controller, pending]);
  return {controller, state, pending, busy: pending || state.phase === 'verifying' || state.refresh === 'working'};
}
export type CreativeSelectionOwner = ReturnType<typeof useCreativeSelection>;
