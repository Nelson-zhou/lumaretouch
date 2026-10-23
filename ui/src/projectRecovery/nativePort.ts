import {invoke} from '@tauri-apps/api/core';
import type {RecoveryPort} from './model';
/** App-lifetime receipt owner must survive hiding the recovery panel. */
export const recoveryNativePort: RecoveryPort = {
  send: request => invoke('project_recovery_request', {request}),
  read: requestId => invoke('project_recovery_status', {requestId}),
};
