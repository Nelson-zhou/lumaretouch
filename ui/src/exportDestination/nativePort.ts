import {originalFormatPlan, type DestinationPolicy, type DestinationPreview} from './model';
/** Inject the app's real invoke. Preview waits for the correlated engine result,
 * never mistakes requested:true for a completed plan. Registration is gated. */
export type Invoke = <T>(command: string, payload: Record<string, unknown>) => Promise<T>;
type Receipt<T> = {status: 'pending' | 'ready' | 'failed'; value?: T; error?: string};
export const destinationPort = (invoke: Invoke) => {
  async function request<T>(payload: Record<string, unknown>): Promise<T> {
    const requestId = crypto.randomUUID();
    try {
      await invoke<{requested: boolean}>('export_destination', {...payload, requestId});
      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        const receipt = await invoke<Receipt<T>>('export_destination_result', {requestId});
        if (receipt.status === 'failed') throw new Error(receipt.error ?? '导出位置预览失败');
        if (receipt.status === 'ready' && receipt.value !== undefined) return receipt.value;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw new Error('导出位置预览超时，请重新预览');
    } finally {
      await invoke('export_destination_release', {requestId}).catch(() => undefined);
    }
  }
  return {
    preview: async (policy: DestinationPolicy, documentIds: string[], intentRevision: number,
              exportOptions: Record<string, unknown>) => {
      const original = exportOptions.format === 'original';
      if (original && (Object.hasOwn(exportOptions, 'bit_depth') || !documentIds.length
          || new Set(documentIds).size !== documentIds.length)) throw new Error('Original 需要明确文档身份，且不能手动指定 bit_depth');
      const result = await request<DestinationPreview>({action: 'preview', policy, documentIds, intentRevision, exportOptions});
      originalFormatPlan(result, original);
      return result;
    },
    cancel: () => request<{cancelled: boolean}>({action: 'cancel'}),
  };
};
