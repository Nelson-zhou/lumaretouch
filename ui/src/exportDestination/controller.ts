import type {DestinationPolicy, DestinationPreview} from './model';
import type {destinationPort} from './nativePort';
/** The host supplies its existing export submit and edit barrier. No export is
 * performed by preview; frame receipts and names are created only by the engine.
 */
export class DestinationFlow {
  private serial = 0;
  private previewValue: DestinationPreview | null = null;
  private submitting = false;
  constructor(private port: ReturnType<typeof destinationPort>) {}
  invalidate() { this.serial++; this.previewValue = null; }
  async preview(policy: DestinationPolicy, ids: string[], revision: number,
                options: Record<string, unknown>, editBarrier: () => Promise<void>) {
    this.invalidate(); const serial = this.serial;
    await editBarrier();
    if (serial !== this.serial) return null;
    const result = await this.port.preview(structuredClone(policy), [...ids], revision, structuredClone(options));
    if (serial !== this.serial || result.intent_revision !== revision) return null;
    this.previewValue = result; return result;
  }
  async submit(revision: number,
               submitExistingExport: (destinationPlanId: string, revision: number) => Promise<unknown>) {
    const plan = this.previewValue;
    if (this.submitting || !plan || plan.intent_revision !== revision) throw new Error('请重新预览导出位置');
    if (plan.entries.some(e => e.disposition === 'needs_confirmation')) {
      throw new Error('请在导出设置中确认改名或跳过冲突文件，再重新预览');
    }
    this.submitting = true;
    try { return await submitExistingExport(plan.plan_id, revision); }
    finally { this.submitting = false; this.invalidate(); }
  }
  async close() { this.invalidate(); await this.port.cancel(); }
}
