import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {commonBackgroundPreview, commonBackgroundPreviewStatus, commonBackgroundApply, commonBackgroundResult, INSPECTION_EDIT_INTENT} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createWorkflow, type Context, type Transport} from './workflow';
import {defaultDraft} from './model';

let ownIntent = false;
const api: Transport = {
  preview: (action, previewId, sessionId, documentId, mutation) => commonBackgroundPreview({action, previewId, sessionId, documentId, mutation}),
  status: previewId => commonBackgroundPreviewStatus(previewId),
  submit: async request => {
    await settleCurveEdit();
    ownIntent = true;
    try {return commonBackgroundApply(request);} finally {ownIntent = false;}
  },
  result: requestId => commonBackgroundResult(requestId),
};

/** Keep this owner mounted in App, not in a collapsible/search-filtered tool panel. */
export function useCommonBackgroundWorkflow(context: Context, refresh: () => Promise<void>, prepare?: () => void | Promise<void>) {
  const latest = useRef(refresh), before = useRef(prepare);
  latest.current = refresh; before.current = prepare;
  const workflow = useMemo(() => createWorkflow(api, () => latest.current(), {
    prepare: async () => {await before.current?.(); await settleCurveEdit();},
  }), []);
  const [state, setState] = useState(workflow.snapshot());
  const [draft, setDraft] = useState(defaultDraft);
  useEffect(() => {setDraft(defaultDraft());}, [context.documentId]);
  useLayoutEffect(() => {
    workflow.activate(); setState(workflow.snapshot()); const off = workflow.subscribe(setState);
    return () => {off(); workflow.stop();};
  }, [workflow]);
  useLayoutEffect(() => {workflow.context(context);}, [workflow, context.enabled, context.canStart, context.documentId, context.contextKey, context.reason]);
  useEffect(() => {
    const edit = () => {if (!ownIntent) workflow.externalEdit();};
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && workflow.snapshot().open) {event.preventDefault(); workflow.cancel();}
    };
    window.addEventListener(INSPECTION_EDIT_INTENT, edit); window.addEventListener('keydown', escape);
    return () => {window.removeEventListener(INSPECTION_EDIT_INTENT, edit); window.removeEventListener('keydown', escape);};
  }, [workflow]);
  return {workflow, state, context, draft, setDraft, active: state.open, pending: workflow.busy()};
}
export type CommonBackgroundOwner = ReturnType<typeof useCommonBackgroundWorkflow>;
