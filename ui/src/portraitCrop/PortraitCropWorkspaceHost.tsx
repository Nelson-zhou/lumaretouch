// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore} from 'react';
import {PortraitCropController} from './controller';
import {PortraitCropPanel} from './PortraitCropPanel';
import {createPortraitCropTransport} from './transport';
import {RulePresetCatalogue} from './rulePresets/controller';
import {createRulePresetTransport} from './rulePresets/transport';
export type PortraitCropWorkspaceHostProps = {
  /** Exact source/document/epoch/revision/edit/repair/analysis identity; not a file path. */
  contextKey: string | null;
  /** External readiness only. Do not include this controller's own busy bit. */
  enabled: boolean;
  onChanged: () => void | Promise<unknown>;
  onBusy?: (busy: boolean) => void;
  /** Existing confirmed project picker/reopen flow; never a new project writer. */
  onReopenProject?: () => void | Promise<unknown>;
};
/** Mount once for the App lifetime, including while its overlay is closed. */
export function PortraitCropWorkspaceHost({contextKey, enabled, onChanged, onBusy, onReopenProject}: PortraitCropWorkspaceHostProps) {
  const [open, setOpen] = useState(false);
  const [reopening, setReopening] = useState(false), [reopenError, setReopenError] = useState('');
  const dialog = useRef<HTMLDivElement>(null);
  const reopenPending = useRef(false);
  const live = useRef({contextKey, enabled, onChanged, onBusy, open});
  live.current = {contextKey, enabled, onChanged, onBusy, open};
  const controller = useMemo(() => new PortraitCropController(createPortraitCropTransport({
    canUse: () => live.current.enabled && live.current.open,
    contextKey: () => live.current.contextKey,
  }), () => live.current.onChanged()), []);
  const catalogue = useMemo(() => new RulePresetCatalogue(createRulePresetTransport()), []);
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  useLayoutEffect(() => {controller.setContext(contextKey); controller.setEnabled(enabled);}, [controller, contextKey, enabled]);
  useLayoutEffect(() => {live.current.onBusy?.(open || state.pending !== null);}, [open, state.pending]);
  useLayoutEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.focus();
    return () => {if (previous?.isConnected) previous.focus();};
  }, [open]);
  async function reopenProject() {
    if (!onReopenProject || reopenPending.current || !state.pending || state.phase !== 'uncertain') return;
    reopenPending.current = true; setReopening(true); setReopenError('');
    try {
      await onReopenProject();
      // Picker/callback completion alone is NOT proof of canonical reload.
      await controller.reconcile();
    } catch (error) {setReopenError(error instanceof Error ? error.message : '工程重开尚未确认，原请求仍保留。');}
    finally {reopenPending.current = false; setReopening(false);}
  }
  const close = () => {
    // The panel has already called dismiss. Mark closed synchronously so an
    // awaiting pre-send curve barrier cannot enqueue new read work after close.
    live.current.open = false; setOpen(false);
  };
  return <>
    <button type="button" className="portrait-crop-launch" data-portrait-crop-workflow disabled={!enabled && !state.pending}
      onClick={() => {live.current.open = true; setOpen(true);}}>
      {state.pending ? '人像构图 · 原请求待核对' : '人像构图'}
    </button>
    {open && <div ref={dialog} className="portrait-crop-overlay" data-portrait-crop-workflow role="dialog" aria-modal="true" aria-label="当前照片人像构图" tabIndex={-1}
      onKeyDown={event => {
        if (event.key === 'Escape') {event.stopPropagation(); controller.dismiss(); close(); return;}
        if (event.key !== 'Tab') return;
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')).filter(item => item.getClientRects().length > 0);
        if (!controls.length) {event.preventDefault(); event.currentTarget.focus(); return;}
        const first = controls[0], last = controls[controls.length - 1], focused = document.activeElement;
        if (event.shiftKey && (focused === first || focused === event.currentTarget)) {event.preventDefault(); last.focus();}
        else if (!event.shiftKey && (focused === last || focused === event.currentTarget)) {event.preventDefault(); first.focus();}
      }}>
      {onReopenProject && state.pending && state.phase === 'uncertain' && <section className="portrait-crop-reopen" data-portrait-crop-workflow aria-label="重新打开工程以恢复工作区">
        <p>重新打开已保存工程将舍弃未保存编辑，原操作结果不会据此改称失败。</p>
        <button type="button" disabled={reopening} onClick={() => void reopenProject()}>{reopening ? '正在等待工程重开确认…' : '通过现有工程流程重新打开'}</button>
        {reopenError && <p role="alert">{reopenError}</p>}
      </section>}
      <PortraitCropPanel controller={controller} catalogue={catalogue} disabled={!enabled} onClose={close}/>
    </div>}
  </>;
}
