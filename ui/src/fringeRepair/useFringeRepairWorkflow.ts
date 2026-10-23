import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT, notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createFringeWorkflow, type FringeContext} from './workflow';
import type {FringeTransport} from './protocol';

let ownIntent = false;
const transport: FringeTransport = {
  preview: (action, previewId, sessionId, documentId, mutation) =>
    invoke('fringe_repair_preview', {action, previewId, sessionId, documentId, mutation: mutation ?? null}),
  status: previewId => invoke('fringe_repair_preview_status', {previewId}),
  submit: (request, clientGeneration) => {
    // No deferred barrier here: workflow rechecks its lifetime after settling it.
    ownIntent = true;
    try {
      notifyInspectionEditIntent();
      return invoke('fringe_repair', {requestId: request.request_id, previewId: request.preview_id,
        sessionId: request.session_id, documentId: request.document_id, clientGeneration});
    } finally {ownIntent = false;}
  },
  result: requestId => invoke('fringe_repair_result', {requestId}),
  audit: () => invoke('fringe_repair_audit'),
};

/** Mount at App scope. A collapsed tool panel never owns an outstanding apply. */
export function useFringeRepairWorkflow(context: FringeContext, refresh: () => Promise<void>, prepare?: () => void | Promise<void>) {
  const refreshRef = useRef(refresh), prepareRef = useRef(prepare);
  refreshRef.current = refresh; prepareRef.current = prepare;
  const workflow = useMemo(() => createFringeWorkflow(transport, {
    refresh: () => refreshRef.current(),
    prepare: async () => {await prepareRef.current?.(); await settleCurveEdit();}, beforeSubmit: settleCurveEdit,
  }), []);
  const [state, setState] = useState(workflow.snapshot());
  useLayoutEffect(() => {
    workflow.activate(); setState(workflow.snapshot()); const off = workflow.subscribe(setState);
    return () => {off(); workflow.stop();};
  }, [workflow]);
  useLayoutEffect(() => {workflow.context(context);},
    [workflow, context.enabled, context.canStart, context.documentId, context.contextKey, context.reason]);
  useEffect(() => {void workflow.initialize();}, [workflow]);
  useEffect(() => {
    const edit = () => {if (!ownIntent) workflow.externalEdit();};
    const key = (event: KeyboardEvent) => {
      const snapshot = workflow.snapshot();
      if (event.key === 'Escape' && (snapshot.open || snapshot.phase === 'preparing')) {
        event.preventDefault(); event.stopPropagation(); workflow.cancel(); return;
      }
      const target = event.target as HTMLElement | null;
      const typing = target?.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName ?? '');
      if (snapshot.open && (event.ctrlKey || event.metaKey) && !event.altKey &&
          ['z', 'y'].includes(event.key.toLowerCase())) {
        event.preventDefault(); event.stopImmediatePropagation();
        if (snapshot.strokeActive) workflow.cancelStroke('撤销了当前未完成的范围笔迹。');
        else if (!workflow.busy() && !event.repeat && event.key.toLowerCase() === 'z' && !event.shiftKey && snapshot.draft?.strokes.length)
          workflow.edit({...snapshot.draft, strokes: snapshot.draft.strokes.slice(0, -1)});
        return; // Document history must not run behind this uncommitted modal.
      }
      if (!typing && event.key.toLowerCase() === 'm' && event.shiftKey && (event.ctrlKey || event.metaKey) &&
          !event.altKey && !event.repeat && context.enabled && context.canStart !== false && !snapshot.open && !workflow.busy()) {
        event.preventDefault(); event.stopPropagation(); void workflow.start();
      }
    };
    window.addEventListener(INSPECTION_EDIT_INTENT, edit); window.addEventListener('keydown', key, true);
    return () => {window.removeEventListener(INSPECTION_EDIT_INTENT, edit); window.removeEventListener('keydown', key, true);};
  }, [workflow, context.enabled, context.canStart]);
  return {workflow, state, context, active: state.open, pending: workflow.busy()};
}
export type FringeRepairOwner = ReturnType<typeof useFringeRepairWorkflow>;
