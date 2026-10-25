// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import type {DocState, EngineStatus} from '../native';
import type {ToolActivity} from '../toolRouting/RetouchToolActivity';
import {createHairColourPort} from '../hairColour/nativePort';
import type {HairPort} from '../hairColour/model';
import {createHairUnificationPort, type HairUnificationPort} from '../hairUnification/nativePort';
import {HairUnificationPanel} from '../hairUnification/HairUnificationPanel';
import {binding as unificationBinding} from '../hairUnification/model';
import {createHairVolumePort, type HairVolumePort} from './nativePort';
import {HairVolumePanel} from './HairVolumePanel';
import {binding as volumeBinding} from './model';
import {hairFamilyAdmission, hairReviewBusy, hairVolumeProtocol, type HairFamilyMember} from './familyAdmission';

type Inputs = {
  status: EngineStatus | null;
  doc: DocState | null;
  peopleEnabled: boolean;
  /** Other tools only. Never include a hair-family request's own pending state. */
  externalBusy: boolean;
  refresh: () => Promise<void>;
  engineAlive: boolean;
  onStartEngine: () => Promise<void>;
};
type FamilyPorts = {colour: HairPort; unification: HairUnificationPort; volume: HairVolumePort};
const protocolField = {colour: 'hair_colour_protocol', unification: 'hair_unification_protocol', volume: 'hair_volume_protocol'} as const;
const colourBusy = (port: HairPort) => {
  const state = port.snapshot();
  return state.pending || state.checking || state.uncertain;
};

/** App lifetime only. Existing family ports retain their queues, exact receipts and canonical-history owner. */
export function useHairFamily(inputs: Inputs) {
  const live = useRef(inputs); live.current = inputs;
  const ports = useMemo(() => {
    const family = {} as FamilyPorts;
    const canUse = (member: HairFamilyMember) => {
      const {status, doc, peopleEnabled, externalBusy} = live.current;
      const protocolReady = member === 'volume'
        ? hairVolumeProtocol(status?.ready_caps?.hair_volume_protocol, status?.ready_caps?.hair_volume_capability)
        : status?.ready_caps?.[protocolField[member]] === 1;
      const ready = peopleEnabled && !!status?.engine_alive && protocolReady
        && !externalBusy && !!doc?.document_id && status.image?.load_id === doc.document_id
        && !status.edit_queue?.in_flight && !status.edit_queue?.pending && !status.edit_queue?.closed;
      // Query sibling snapshots at admission, not one-render-old booleans or the request's own reservation.
      return hairFamilyAdmission(member, ready, {
        colour: colourBusy(family.colour),
        unification: hairReviewBusy(family.unification.snapshot()),
        volume: hairReviewBusy(family.volume.snapshot()),
      });
    };
    const refresh = () => live.current.refresh();
    family.colour = createHairColourPort(() => canUse('colour'), refresh);
    family.unification = createHairUnificationPort(() => canUse('unification'), refresh);
    family.volume = createHairVolumePort(() => canUse('volume'), refresh);
    return family;
  }, []);
  const colour = useSyncExternalStore(ports.colour.subscribe, ports.colour.snapshot, ports.colour.snapshot);
  const unification = useSyncExternalStore(ports.unification.subscribe, ports.unification.snapshot, ports.unification.snapshot);
  const volume = useSyncExternalStore(ports.volume.subscribe, ports.volume.snapshot, ports.volume.snapshot);
  const people = inputs.doc?.people ?? null;
  const unificationKey = unificationBinding(people).key, volumeKey = volumeBinding(people).key;
  useLayoutEffect(() => {ports.unification.context(people);}, [ports, unificationKey]);
  useLayoutEffect(() => {ports.volume.context(people);}, [ports, volumeKey]);
  const colourLocked = colour.pending || colour.checking || colour.uncertain;
  const unificationLocked = hairReviewBusy(unification), volumeLocked = hairReviewBusy(volume);
  const workflowBusy = colourLocked || unificationLocked || volumeLocked;
  const baseBusy = inputs.externalBusy || !!inputs.status?.edit_queue?.in_flight
    || !!inputs.status?.edit_queue?.pending || !!inputs.status?.edit_queue?.closed;
  const slots = {
    hairUnificationPanel: <HairUnificationPanel port={ports.unification} engineAlive={inputs.engineAlive} onStartEngine={inputs.onStartEngine}
      busy={baseBusy || colourLocked || volumeLocked} available={inputs.status?.ready_caps?.hair_unification_protocol === 1}/>,
    hairVolumePanel: <HairVolumePanel port={ports.volume} engineAlive={inputs.engineAlive} onStartEngine={inputs.onStartEngine}
      busy={baseBusy || colourLocked || unificationLocked} available={hairVolumeProtocol(inputs.status?.ready_caps?.hair_volume_protocol, inputs.status?.ready_caps?.hair_volume_capability)}/>,
    hairPort: ports.colour,
    hairBusy: baseBusy || unificationLocked || volumeLocked,
    hairWorkflowBusy: workflowBusy,
    refreshHair: inputs.refresh,
  };
  const activities: ToolActivity[] = [
    {name: '颅顶与两侧发量', featureId: 'PC-32472', path: '颅顶 / 两侧发量', active: volume.open,
      pending: volume.pending || volume.checking || volume.preparing || volume.refreshing,
      phase: volume.uncertain ? 'uncertain' : volume.phase, message: volume.message, check: () => ports.volume.recover()},
    {name: '发色统一', featureId: 'PC-32472', path: '发色统一', active: unification.open,
      pending: unification.pending || unification.checking || unification.preparing || unification.refreshing,
      phase: unification.uncertain ? 'uncertain' : unification.phase, message: unification.message, check: () => ports.unification.recover()},
    {name: '发色与光泽', featureId: 'PC-32472', path: '发色选择', active: false, pending: colour.pending || colour.checking,
      phase: colour.uncertain ? 'uncertain' : 'idle', message: colour.message, check: () => ports.colour.recover().catch(() => undefined)},
  ];
  return {ports, colour, unification, volume, workflowBusy, unificationLocked, volumeLocked, slots, activities};
}
