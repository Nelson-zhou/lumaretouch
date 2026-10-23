// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import {runPeopleRequest, type DocState, type EngineStatus} from '../native';
import {createPeopleWorkflow} from './workflow';
import {type PeopleAction, type PeopleMailbox, type PeopleTarget} from './model';

/** App lifetime keeps the original request queryable when the panel is collapsed. */
export function usePeopleWorkflow(status: EngineStatus | null, doc: DocState | null, refresh: () => Promise<void>) {
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  const workflow = useMemo(() => createPeopleWorkflow({
    send: command => runPeopleRequest(command),
    read: request_id => runPeopleRequest({action: 'status', request_id}) as Promise<PeopleMailbox>,
    refresh: () => refreshRef.current(),
  }), []);
  const state = useSyncExternalStore(workflow.subscribe, workflow.snapshot, workflow.snapshot);
  const value = doc?.people ?? null;
  const supported = status?.ready_caps?.people_protocol === 1;
  const enabled = !!status?.engine_alive && supported && !!value && !status?.export_progress;
  useLayoutEffect(() => {workflow.update(value, enabled);}, [workflow, value, enabled]);
  function submit(action: PeopleAction['action'], payload: Record<string, unknown>, target: PeopleTarget): Promise<void> {
    if (!value) return Promise.reject(Error('当前照片尚未提供人物状态。'));
    const {document_id, document_epoch, document_revision} = value.binding;
    return workflow.submit({document_id, document_epoch, document_revision,
      state_revision: value.revision, association_revision: value.association_revision,
      request_id: crypto.randomUUID(), target, action, payload});
  }
  return {value, state, supported, enabled, submit, submitCaptured: workflow.submit, patch: workflow.patch, check: workflow.check};
}
export type PeopleOwner = ReturnType<typeof usePeopleWorkflow>;
