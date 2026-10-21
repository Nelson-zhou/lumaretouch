/** Match a request/document/sequence, never infer an original frame from a delay. */
export interface SnapshotFrame { seq: number; w: number; h: number; pixelLen: number; pixels: Uint8Array; y0: number; rows: number }
export interface CompareReceipt { capture_id: string | null; doc: string; seq: number; view: string }
export async function captureOriginal<T extends SnapshotFrame>(o: {
  id: string; doc: string; cancelled: () => boolean;
  request: (id: string) => Promise<unknown>; receipt: () => Promise<CompareReceipt | null>;
  pixels: () => Promise<T>; wait: () => Promise<void>; now: () => number; timeoutMs?: number;
}): Promise<T | null> {
  const end = o.now() + (o.timeoutMs ?? 10000);
  if (o.cancelled()) return null;
  await o.request(o.id);
  while (!o.cancelled()) {
    if (o.now() >= end) throw new Error('原图读取超时，请重试对比');
    const receipt = await o.receipt();
    if (receipt?.capture_id === o.id && receipt.doc === o.doc && receipt.view === 'original') {
      const frame = await o.pixels();
      if (o.cancelled()) return null;
      if (frame.seq === receipt.seq && frame.w > 0 && frame.h > 0 && frame.y0 === 0
        && frame.rows === frame.h && frame.pixelLen === frame.w * frame.h * 4
        && frame.pixels.byteLength === frame.pixelLen) return frame;
    }
    await o.wait();
  }
  return null;
}
export function compareImageKey(image: {doc?: string; load_id?: string; w: number; h: number; src_w: number; src_h: number} | null | undefined): string {
  return image ? JSON.stringify([image.doc, image.load_id, image.w, image.h, image.src_w, image.src_h]) : '';
}

/** Side-by-side uses two whole frames at identical scale. */
export function comparisonFrameSize(w:number,h:number,mode:'single'|'split'|'swipe') {
  return {w:mode==='split'?w*2:w,h};
}
