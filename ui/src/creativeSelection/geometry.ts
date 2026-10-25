// SPDX-License-Identifier: GPL-3.0-or-later
import type {SelectionCanvas, SelectionCombine, SelectionOperation, SelectionPoint} from './model';
export type SelectionConstraint = {mode: 'free'} | {mode: 'ratio'; width: number; height: number}
  | {mode: 'size'; width: number; height: number};
export interface SelectionRect {left: number; top: number; width: number; height: number}
/** CSS client coordinates map to full frozen canvas edges; neither DPR nor preview dimensions enter the recipe. */
export function selectionPoint(clientX: number, clientY: number, rect: SelectionRect, canvas: SelectionCanvas): SelectionPoint | null {
  if (![clientX, clientY, rect.left, rect.top, rect.width, rect.height, canvas.width, canvas.height].every(Number.isFinite)
    || canvas.width <= 0 || canvas.height <= 0 || rect.width <= 0 || rect.height <= 0
    || clientX < rect.left || clientY < rect.top || clientX > rect.left + rect.width || clientY > rect.top + rect.height) return null;
  return [(clientX - rect.left) / rect.width * canvas.width, (clientY - rect.top) / rect.height * canvas.height];
}
export function selectionShape(kind: 'rectangle' | 'ellipse', combine: SelectionCombine, start: SelectionPoint, end: SelectionPoint,
  canvas: SelectionCanvas, constraint: SelectionConstraint): SelectionOperation | null {
  if (![canvas.width, canvas.height, ...start, ...end].every(Number.isFinite) || canvas.width <= 0 || canvas.height <= 0
    || [start, end].some(point => point[0] < 0 || point[0] > canvas.width || point[1] < 0 || point[1] > canvas.height)) return null;
  let x0: number, y0: number, x1: number, y1: number;
  if (constraint.mode === 'size') {
    const {width, height} = constraint;
    if (![width, height].every(Number.isFinite) || width <= 0 || height <= 0 || width > canvas.width || height > canvas.height) return null;
    // Keep the requested size at the canvas edge, rather than silently shrinking it.
    x0 = Math.max(0, Math.min(canvas.width - width, start[0])); y0 = Math.max(0, Math.min(canvas.height - height, start[1]));
    x1 = x0 + width; y1 = y0 + height;
  } else {
    let dx = end[0] - start[0], dy = end[1] - start[1];
    if (constraint.mode === 'ratio') {
      if (![constraint.width, constraint.height].every(Number.isFinite) || constraint.width <= 0 || constraint.height <= 0) return null;
      const ratio = constraint.width / constraint.height, sx = dx < 0 ? -1 : 1, sy = dy < 0 ? -1 : 1;
      if (!Number.isFinite(ratio) || ratio < 1e-6 || ratio > 1e6) return null;
      let width = Math.max(Math.abs(dx), Math.abs(dy) * ratio), height = width / ratio;
      const availableX = sx > 0 ? canvas.width - start[0] : start[0], availableY = sy > 0 ? canvas.height - start[1] : start[1];
      const scale = Math.min(1, availableX / (width || 1), availableY / (height || 1));
      width *= scale; height *= scale; dx = width * sx; dy = height * sy;
    }
    x0 = Math.min(start[0], start[0] + dx); x1 = Math.max(start[0], start[0] + dx);
    y0 = Math.min(start[1], start[1] + dy); y1 = Math.max(start[1], start[1] + dy);
  }
  if (!(x1 > x0 && y1 > y0)) return null;
  return {kind, combine, x0, y0, x1, y1};
}
export function sameSelectionRect(a: SelectionRect, b: SelectionRect): boolean {
  return a.left === b.left && a.top === b.top && a.width === b.width && a.height === b.height;
}
export function selectionTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && !!target.closest('input, textarea, select, button, [contenteditable]:not([contenteditable="false"]), [role="textbox"]');
}
