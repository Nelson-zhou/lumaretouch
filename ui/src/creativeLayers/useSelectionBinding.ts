// SPDX-License-Identifier: GPL-3.0-or-later
import {useCreativeSelection} from '../creativeSelection/useCreativeSelection';
import {creativeSelectionNativePort} from '../creativeSelection/nativePort';
import type {CreativeWorkspaceOwner} from './useCreativeWorkspace';

/** App-lifetime selection owner, distinct local vector drafts and shared canonical history. */
export function useSelectionBinding(owner: CreativeWorkspaceOwner, scope: string, active: boolean, available: boolean, externalBusy: boolean) {
  const authority = owner.value?.authority;
  const document = authority?.document;
  const layer = document?.layers.find(item => item.id === document.selected_id);
  const binding = authority && document && layer?.kind === 'image' ? {
    document_id: document.document_id, source_uid: document.source_uid,
    ownership_token: authority.ownership_token, expected_revision: document.revision, layer_id: layer.id,
  } : null;
  return useCreativeSelection({scope, binding, active, available, busy: owner.busy || externalBusy},
    creativeSelectionNativePort, (reply, request) => owner.acceptSelection(reply, request));
}
