// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import type {PeopleView} from '../people/model';
import {binding} from './model';
import {createHairUnificationPort} from './nativePort';

/** Mount once in App. Panel unmounts must never clear the request or source-owned samples. */
export function useHairUnificationPort(enabled: boolean, refresh: () => Promise<void>, people: PeopleView | null) {
  const live = useRef({enabled, refresh}); live.current = {enabled, refresh};
  const port = useMemo(() => createHairUnificationPort(() => live.current.enabled, () => live.current.refresh()), []);
  const context = binding(people);
  useLayoutEffect(() => {port.context(people);}, [port, context.key]);
  const state = useSyncExternalStore(port.subscribe, port.snapshot, port.snapshot);
  return {port, state, check: () => {void port.recover();}};
}
