/** Local-only candidates, no automatic restoration or unknown-write retries. */
export type RecoveryCandidate = {
  candidate_id: string; project_id?: string; phase: 'committed' | 'damaged';
  created_ns?: number; revision?: number; project_sha256?: string;
  project_bytes?: number; kind?: 'autosave' | 'version_snapshot'; reason?: string;
};
export type SourceCheck = {document_id: string; source_asset_id: string; path: string;
  status: 'matched' | 'missing' | 'changed' | 'unverified' | 'unavailable'};
export type Review = {receipt: RecoveryCandidate; sources: SourceCheck[];
  source_reconciliation_required: boolean; original_will_be_overwritten: false};
export type Reply = {request_id: string; project_id: string; action: string;
  success: boolean; outcome_unknown?:boolean; destination?:string; operations?:Array<{phase:string;request:{request_id:string;action:string;destination?:string};result?:{success:boolean;path?:string;error?:string}}> ; candidates?: RecoveryCandidate[]; review?: Review;
  phase?: string; path?: string; error?: string; area?: 'candidates' | 'trash'; usage?: {bytes:number; budget_bytes:number}; receipt?: RecoveryCandidate};
export type Request = {cmd: 'project_recovery'; request_id: string; project_id: string;
  action: 'list' | 'inspect' | 'restore' | 'discard' | 'status' | 'cancel' | 'snapshot' | 'checkpoint' | 'relink' | 'trash_list' | 'restore_trash';
  area?: 'candidates' | 'trash'; source_asset_id?: string; path?: string; candidate_id?: string; reviewed_sha256?: string; destination?: string; confirmed?: boolean};
export type RecoveryPort = {
  send: (request: Request) => Promise<unknown>;
  read: (requestId: string) => Promise<{phase: 'pending' | 'done' | 'unknown' | 'not_sent'; result?: Reply}>;
};
export function createRecoveryWorkflow(port: RecoveryPort) {
  let projectId = '', epoch = 0, pending: Request | null = null;
  let state: {phase: 'idle' | 'working' | 'uncertain' | 'done' | 'error';
    reply?: Reply; error?: string} = {phase: 'idle'};
  const listeners = new Set<() => void>();
  const publish = () => listeners.forEach(fn => fn());
  function updateProject(id: string) {
    if (id === projectId) return;
    projectId = id; epoch++; pending = null; state = {phase: 'idle'}; publish();
  }
  async function read() {
    if (!pending) return;
    const request = pending, generation = epoch;
    try {
      const receipt = await port.read(request.request_id);
      if (generation !== epoch || pending !== request) return;
      if (receipt.phase === 'not_sent') {
        pending = null; state = {phase:'error', error:state.error ?? '请求未发送，可在条件满足后重试'};
      } else if (receipt.phase !== 'done' || !receipt.result) {
        state = {phase: 'uncertain', error: '结果待确认。请查询原请求，不要重复恢复或丢弃。'};
      } else {
        const result = receipt.result;
        if (result.request_id !== request.request_id || result.project_id !== request.project_id || result.action !== request.action)
          throw Error('恢复回执身份不匹配');
        if(result.outcome_unknown){state={phase:'uncertain',reply:result,error:`${result.error??'结果未知'} ${result.destination??''}。保留该目标，重开后检查本机操作记录；不会重发。`};publish();return;}
        pending = null;
        state = result.success ? {phase: 'done', reply: result} : {phase: 'error', error: result.error ?? '操作失败'};
      }
    } catch (error) {
      if (generation === epoch) state = {phase: 'uncertain', error: String(error)};
    }
    if (generation === epoch) publish();
  }
  async function run(action: Request['action'], details: Omit<Partial<Request>, 'action' | 'project_id' | 'request_id' | 'cmd'> = {}) {
    if (!projectId || pending) return;
    if ((['restore','restore_trash','discard','relink'].includes(action)) && details.confirmed !== true)
      throw Error('请先明确确认恢复为副本或移入恢复回收站');
    const generation = epoch;
    const request: Request = {...details, cmd: 'project_recovery', project_id: projectId,
      request_id: crypto.randomUUID(), action};
    pending = request; state = {phase: 'working'}; publish();
    try { await port.send(request); }
    catch (error) {
      if (generation === epoch) {state = {phase: 'uncertain', error: String(error)}; publish();await read();}
      return;
    }
    if (generation === epoch) await read();
  }
  return {updateProject, run, read, snapshot: () => state,
    subscribe: (fn: () => void) => {listeners.add(fn); return () => {listeners.delete(fn);};}};
}
