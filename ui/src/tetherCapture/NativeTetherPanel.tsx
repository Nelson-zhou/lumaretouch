// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState} from 'react';
import {TetherCapturePanel} from './TetherCapturePanel';
import {connectNativeTether} from './nativePort';
import type {TetherHostPort, TetherImportNotice} from './protocol';

/** Unmount detaches UI only; the native owner keeps pending receipts/session. */
export function NativeTetherPanel({onImported}: {onImported: (notice: TetherImportNotice) => void}) {
  const [host, setHost] = useState<TetherHostPort | null>(null);
  const [error, setError] = useState('正在读取真实联机宿主状态，不会启动快门或取景。');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    void connectNativeTether().then(value => { if (active) setHost(value); }, reason => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { active = false; };
  }, [attempt]);
  return <>
    <TetherCapturePanel host={host} unavailableReason={error} onImportedDocument={onImported}/>
    {!host && <button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取联机宿主</button>}
  </>;
}
