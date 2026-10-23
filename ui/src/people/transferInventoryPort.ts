import {invoke} from '@tauri-apps/api/core';
import type {InventoryMailbox, InventoryTransport} from './transferInventoryWorkflow';

/** Same native batch mailbox, deliberately bypassing edit-intent notifications for this read. */
export const peopleInventoryPort: InventoryTransport = {
  request: (docs, requestId) => invoke<{requested: boolean}>('batch', {action: 'people_targets', docs, requestId}),
  read: requestId => invoke<InventoryMailbox>('batch_result', {requestId}),
};
