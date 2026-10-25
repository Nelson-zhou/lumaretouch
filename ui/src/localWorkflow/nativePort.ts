import type {ReviewImagePage} from './presetReview';
// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import type {PreflightReport, WorkflowDefinition, WorkflowHostPort, WorkflowReceipt, WorkflowRun, WorkflowWorkspace} from './contracts';

/** Read the real journal identity before allowing controller recovery queries. */
export async function connectNativeWorkflow(): Promise<WorkflowHostPort> {
  const workspace = await invoke<WorkflowWorkspace>('local_workflow_workspace');
  if (workspace.port_version !== 1 || !workspace.host_scope_id) throw new Error('本地工作流宿主版本或恢复日志身份不可用。');
  return {
    version: 1,
    scope_id: workspace.host_scope_id,
    readWorkspace: () => invoke<WorkflowWorkspace>('local_workflow_workspace'),
    refreshCatalogue: () => invoke<WorkflowWorkspace>('local_workflow_workspace', {refreshCatalogue: true}),
    readDefinition: workflowId => invoke<WorkflowDefinition>('local_workflow_definition', {workflowId}),
    preflight: input => invoke<PreflightReport>('local_workflow_preflight', {input}),
    submit: input => invoke<WorkflowReceipt>('local_workflow_submit', {input}),
    queryRequest: requestId => invoke<WorkflowReceipt>('local_workflow_request', {requestId}),
    readRun: runId => invoke<WorkflowRun>('local_workflow_run', {runId}),
    readReviewImage: input => invoke<ReviewImagePage>('local_workflow_review_image', {input}),
  };
}
