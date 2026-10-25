// SPDX-License-Identifier: GPL-3.0-or-later
import {validRect, type NeckRect} from './model';
export type CropFields = [string, string, string, string];
export const emptyCropFields = (): CropFields => ['', '', '512', '512'];
export function cropRect(fields: CropFields, size: [number, number]): NeckRect | null {
  if (!fields.every(value => /^\d+$/.test(value.trim()))) return null;
  const rect = fields.map(Number);
  return validRect(rect, size) ? rect : null;
}
/** Coordinates are explicit. Neither a face box nor pose estimates choose a neck. */
export function NeckCropFields({fields, size, label, disabled, onChange}: {
  fields: CropFields; size: [number, number]; label: string; disabled: boolean; onChange: (fields: CropFields) => void;
}) {
  return <fieldset disabled={disabled}><legend>{label}，完整画幅 {size[0]} × {size[1]}</legend>
    {(['左 x', '上 y', '宽', '高'] as const).map((name, index) => <label key={name}>{name}<input type="number"
      min={index < 2 ? 0 : 1} max={index < 2 ? size[index] - 1 : Math.min(1024, size[index - 2])} step={1}
      value={fields[index]} aria-label={`${label} ${name}`} onChange={event => {
        const next: CropFields = [...fields]; next[index] = event.target.value; onChange(next);
      }}/></label>)}
    {!cropRect(fields, size) && <p>请输入画幅内的整数像素边界；单边至多 1024，裁片不缩放。位置留空不会猜测颈部。</p>}
  </fieldset>;
}
