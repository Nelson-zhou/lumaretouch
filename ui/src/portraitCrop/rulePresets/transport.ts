// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import type {Transport} from './model';
/** Dedicated local native catalogue, not engine RPC, localStorage or a plugin. */
export const createRulePresetTransport = (): Transport => request => invoke<unknown>('portrait_crop_rules', {request: structuredClone(request)});
