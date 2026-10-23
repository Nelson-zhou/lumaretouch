import {object, readRecipeIdentity, readReview, type FringeMutation, type FringeRequest, type FringeReview} from './model';

export interface FringeTransport {
  preview: (action: 'preview' | 'presented' | 'cancel', preview: string, session: string, document: string, mutation?: FringeMutation) => Promise<unknown>;
  status: (preview: string) => Promise<unknown>;
  submit: (request: FringeRequest, clientGeneration: string) => Promise<unknown>;
  result: (request: string) => Promise<unknown>;
  audit: () => Promise<unknown>;
}
export interface PreviewIdentity {preview: string; session: string; document: string}
export interface WaitOptions {timeout: number; sleep: (ms: number) => Promise<void>; current: () => boolean}
export function bounded<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(Error('等待超时')), Math.max(1, ms));
  })]).finally(() => {if (timer !== undefined) clearTimeout(timer);});
}
export function statusIdentity(raw: unknown, identity: PreviewIdentity): Record<string, unknown> {
  if (!object(raw) || raw.protocol !== 1 || raw.preview_id !== identity.preview ||
      raw.session_id !== identity.session || raw.document_id !== identity.document)
    throw Error('祛边预览身份或协议不符');
  return raw;
}
export async function awaitReview(api: FringeTransport, identity: PreviewIdentity, options: WaitOptions): Promise<FringeReview | null> {
  const deadline = Date.now() + options.timeout;
  while (options.current()) {
    if (Date.now() >= deadline) throw Error('等待祛边审核图超时');
    const raw = await bounded(api.status(identity.preview), deadline - Date.now());
    if (!options.current()) return null;
    const value = statusIdentity(raw, identity);
    if (['pending', 'running'].includes(String(value.state))) {
      await bounded(options.sleep(80), deadline - Date.now()); continue;
    }
    if (value.state !== 'ready' || value.success !== true)
      throw Error(typeof value.error === 'string' ? value.error : '祛边照片预览未完成');
    return readReview(value);
  }
  return null;
}
export async function acknowledgeReview(api: FringeTransport, identity: PreviewIdentity, review: FringeReview, options: WaitOptions): Promise<boolean> {
  const deadline = Date.now() + Math.min(options.timeout, 10000);
  await bounded(api.preview('presented', identity.preview, identity.session, identity.document), deadline - Date.now());
  while (options.current()) {
    if (Date.now() >= deadline) throw Error('等待祛边显示确认超时');
    const raw = await bounded(api.status(identity.preview), deadline - Date.now());
    if (!options.current()) return false;
    const value = statusIdentity(raw, identity), recipe = readRecipeIdentity(value);
    if (recipe.recipe_document_id !== review.recipe_document_id || recipe.recipe_revision !== review.recipe_revision)
      throw Error('已显示的祛边效果不再对应当前照片配方');
    if (value.state === 'presented' && value.success === true) return true;
    if (value.state !== 'ready' || value.success !== true) throw Error('祛边照片显示确认失效');
    await bounded(options.sleep(60), deadline - Date.now());
  }
  return false;
}
