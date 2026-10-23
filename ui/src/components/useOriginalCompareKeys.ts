// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef} from 'react';

/** Hold Space for the original, without stealing typing or modal gestures. */
export function useOriginalCompareKeys(pid: number | null, hold: () => unknown, release: () => unknown) {
  const actions = useRef({hold, release}); actions.current = {hold, release};
  useEffect(() => {
    const busyTarget = (el: EventTarget | null) => {
      const n = el as HTMLElement | null;
      return !!n && (n.tagName === 'INPUT' || n.tagName === 'TEXTAREA'
        || n.tagName === 'SELECT' || n.tagName === 'BUTTON' || n.isContentEditable);
    };
    const down = (e: KeyboardEvent) => {
      if (document.querySelector('.batchReviewBackdrop, .recoveryWorkspace, .liquifyWorkspace, .studioWorkspace, .skyWorkspace, .shoulderWorkspace')) return;
      if (e.code !== 'Space' || e.repeat || busyTarget(e.target)) return;
      e.preventDefault(); void actions.current.hold();
    };
    const up = (e: KeyboardEvent) => {
      if (document.querySelector('.liquifyWorkspace, .studioWorkspace, .skyWorkspace, .shoulderWorkspace')) return;
      if (e.code !== 'Space' || busyTarget(e.target)) return;
      e.preventDefault(); void actions.current.release();
    };
    window.addEventListener('keydown', down); window.addEventListener('keyup', up);
    return () => {window.removeEventListener('keydown', down); window.removeEventListener('keyup', up);};
  }, [pid]);
}
