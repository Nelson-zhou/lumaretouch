import {useEffect, useRef, useState} from 'react';
import {createInventoryWorkflow, type InventoryContext, type InventoryUi} from './transferInventoryWorkflow';
import {peopleInventoryPort} from './transferInventoryPort';

export function useTransferInventory(context: InventoryContext) {
  const [ui, setUi] = useState<InventoryUi>({phase: 'idle', contextKey: '', requestId: '', result: null, message: ''});
  const latest = useRef(context); latest.current = context;
  const ref = useRef<ReturnType<typeof createInventoryWorkflow> | null>(null);
  useEffect(() => {
    const workflow = createInventoryWorkflow(peopleInventoryPort, setUi); ref.current = workflow;
    workflow.updateContext(latest.current);
    return () => {ref.current = null; workflow.dispose();};
  }, []);
  useEffect(() => {ref.current?.updateContext(context);}, [context.key, context.enabled]);
  const current = () => {ref.current?.updateContext(latest.current); return ref.current;};
  return {ui, start: () => current()?.start(), query: () => current()?.query(), cancel: () => current()?.cancel()};
}
