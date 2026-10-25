// SPDX-License-Identifier: GPL-3.0-or-later
/** Transport only. Device, mutation and receipt ownership remain native. */
import {invoke} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import {open} from '@tauri-apps/plugin-dialog';
import type {TetherDestination, TetherHostEvent, TetherHostPort, TetherReceipt, TetherSnapshot} from './protocol';

export async function connectNativeTether(): Promise<TetherHostPort> {
  const initial = await invoke<TetherSnapshot>('tether_capture_state');
  if (initial.protocol_version !== 1 || !initial.host_id) throw new Error('联机宿主版本或身份不匹配。');
  const hostId = initial.host_id;
  return {
    protocol_version: 1,
    host_id: hostId,
    supported_preview_modes: ['keep_current'],
    readSnapshot: () => invoke<TetherSnapshot>('tether_capture_state'),
    subscribe(listener) {
      let closed = false;
      let detach: (() => void) | undefined;
      void listen<TetherHostEvent>('tether-capture://event', event => {
        if (!closed) listener(event.payload);
      }).then(unlisten => { if (closed) unlisten(); else detach = unlisten; }).catch(() => {
        // Read-only polling below remains available if event registration fails.
      });
      const poll = setInterval(() => {
        void invoke<TetherSnapshot>('tether_capture_state').then(snapshot => {
          if (!closed) listener({type: 'snapshot', snapshot});
        }).catch(() => { /* Existing UI refresh reports native read failures. */ });
      }, 1500);
      return () => { closed = true; clearInterval(poll); detach?.(); };
    },
    send: request => invoke<TetherReceipt>('tether_capture_request', {request}),
    queryReceipt: requestId => invoke<TetherReceipt | null>('tether_capture_receipt', {requestId}),
    async pickDestination() {
      const path = await open({directory: true, multiple: false, title: '选择联机原片保存目录（不覆盖已有文件）'});
      if (typeof path !== 'string') return null;
      return invoke<TetherDestination>('tether_capture_destination', {path});
    },
  };
}
