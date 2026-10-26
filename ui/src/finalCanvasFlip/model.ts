export interface FlipReport {
  operation_id: 'lnx.final_canvas_flip.v1'; horizontal: boolean; vertical: boolean;
  active: boolean; available: boolean; document_id: string; revision: string;
  coordinate_capture_available: boolean; reason: string | null;
}
export const FLIP_CAPTURE_REASON = '翻转后的坐标捕获尚未接通；请先关闭水平/垂直翻转。已有编辑会保留并正常渲染。';
