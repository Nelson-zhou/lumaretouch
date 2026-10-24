import type {BatchUi} from './batchWorkflow';

/** An uncertain receipt is not completion and must not consume the request's refresh notification. */
export function batchCompletionRequest(state: BatchUi, reported: string): string | null {
  return state.result && ['done', 'error'].includes(state.phase) && state.operation !== 'preflight'
    && state.result.outcome_unknown !== true && reported !== state.result.request_id ? state.result.request_id : null;
}
