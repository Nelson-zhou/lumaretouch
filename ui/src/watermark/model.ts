import {useEffect, useState} from 'react';

export type Orientation = 'landscape' | 'portrait' | 'square';
export const orientations: Orientation[] = ['landscape', 'portrait', 'square'];
export const positions = ['top-left', 'top-center', 'top-right', 'middle-left', 'middle-center', 'middle-right', 'bottom-left', 'bottom-center', 'bottom-right'] as const;
export interface WatermarkProfile {
  kind: 'text' | 'image'; text: string; imagePath: string; fontPath: string; color: string;
  position: typeof positions[number]; opacity: number; size: number; margin: number;
  offsetX: number; offsetY: number; rotation: number; fit: boolean;
}
export interface WatermarkSettings {
  enabled: boolean; alsoClean: boolean; profiles: Record<Orientation, WatermarkProfile>;
}
const defaults = (): WatermarkProfile => ({kind: 'text', text: '© 我的作品', imagePath: '', fontPath: '',
  color: '#ffffff', position: 'bottom-right', opacity: .65, size: .25, margin: .03,
  offsetX: 0, offsetY: 0, rotation: 0, fit: true});
export const initialWatermark = (): WatermarkSettings => ({enabled: false, alsoClean: false,
  profiles: {landscape: defaults(), portrait: defaults(), square: defaults()}});
const key = 'lumaretouch.export-watermark.v1';
function load(): WatermarkSettings {
  const base = initialWatermark();
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? 'null');
    if (!saved || typeof saved.enabled !== 'boolean' || typeof saved.alsoClean !== 'boolean') return base;
    for (const name of orientations) {
      const p = saved.profiles?.[name];
      if (!p || !['text', 'image'].includes(p.kind) || !positions.includes(p.position)) return base;
      for (const field of ['text', 'imagePath', 'fontPath', 'color']) if (typeof p[field] !== 'string') return base;
      for (const field of ['opacity', 'size', 'margin', 'offsetX', 'offsetY', 'rotation']) if (typeof p[field] !== 'number' || !Number.isFinite(p[field])) return base;
      if (typeof p.fit !== 'boolean') return base;
      base.profiles[name] = {...defaults(), ...p};
    }
    return {...base, enabled: saved.enabled, alsoClean: saved.alsoClean};
  } catch { return base; }
}
/** Saved export preference, not a portrait edit or a source-image recipe. */
export function useWatermarkSettings() {
  const [watermark, setWatermark] = useState(load);
  const [storageError, setStorageError] = useState('');
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(watermark)); setStorageError(''); }
    catch { setStorageError('水印设置未能保存；当前会话仍可导出。'); }
  }, [watermark]);
  return {watermark, setWatermark, storageError};
}
