import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CaptureContext, SampleLibraryPort } from './adapter';
import { createNativeSampleLibrary } from './nativePort';
import { errorMessage, parseReference, type SelectedSampleReference } from './model';

/** App-owned immutable identity; choosing a reference does not apply any color operator. */
export function useSampleLibraryHost({ enabled, documentId, refreshKey }: {
  enabled: boolean; documentId: string; refreshKey: string;
}) {
  const [open, setOpen] = useState(false), [mode, setMode] = useState<'manage' | 'reference'>('manage');
  const [selection, setSelection] = useState<{ target: string; reference: Readonly<SelectedSampleReference> } | null>(null);
  const [context, setContext] = useState<{ key: string; value: CaptureContext } | null>(null);
  const [contextError, setContextError] = useState(''), [contextPending, setContextPending] = useState(false);
  const [retry, setRetry] = useState(0);
  const latest = useRef({ enabled, documentId }); latest.current = { enabled, documentId };
  const native = useMemo(() => createNativeSampleLibrary(() => latest.current.enabled), []);
  const port = useMemo<SampleLibraryPort>(() => ({
    ...native.port,
    async snapshot(options) {
      const result = await native.port.snapshot(options);
      setSelection(previous => previous && !result.order_ids.includes(previous.reference.sample_id) ? null : previous);
      return result;
    },
    async command(command, revision, options) {
      const result = await native.port.command(command, revision, options);
      if (command.op === 'sample_remove') setSelection(previous =>
        previous && result.affected_ids.includes(previous.reference.sample_id) ? null : previous);
      return result;
    },
  }), [native]);
  const clearSelectedReference = useCallback(() => setSelection(null), []);
  const setSelectedReference = useCallback((value: SelectedSampleReference | null) => {
    if (!value) { setSelection(null); return; }
    if (!latest.current.enabled || latest.current.documentId !== documentId) return;
    if (typeof value.sample_id !== 'string' || !value.sample_id) throw new Error('样片稳定身份缺失。');
    const verified = parseReference(value);
    const reference = Object.freeze({ ...verified, source: Object.freeze({ ...verified.source }), sample_id: value.sample_id });
    setSelection({ target: documentId, reference });
  }, [documentId]);
  useEffect(() => { setSelection(null); }, [documentId]);
  useEffect(() => {
    if (!enabled) { setOpen(false); setContext(null); setContextPending(false); setSelection(null); return; }
    const controller = new AbortController(); let live = true;
    setContextPending(true); setContextError('');
    void native.context({ signal: controller.signal }).then(value => {
      if (!live) return;
      if (value.load_id !== documentId) throw new Error('当前照片状态正在同步，请刷新当前照片状态。');
      setContext({ key: refreshKey, value });
    }).catch(error => { if (live) { setContext(null); setContextError(errorMessage(error)); } })
      .finally(() => { if (live) setContextPending(false); });
    return () => { live = false; controller.abort(); };
  }, [native, enabled, documentId, refreshKey, retry]);
  return {
    port, open, mode, enabled, documentId, contextError, contextPending,
    captureContext: enabled && !contextPending && context?.key === refreshKey ? context.value : undefined,
    selectedReference: enabled && selection?.target === documentId ? selection.reference : null,
    setSelectedReference, clearSelectedReference,
    show: (next: 'manage' | 'reference' = 'manage') => { if (enabled) { setMode(next); setOpen(true); setRetry(value => value + 1); } },
    close: () => setOpen(false), refreshContext: () => setRetry(value => value + 1),
  };
}
export type SampleLibraryOwner = ReturnType<typeof useSampleLibraryHost>;
