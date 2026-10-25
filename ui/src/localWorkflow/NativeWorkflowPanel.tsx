// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState, useSyncExternalStore} from 'react';
import {open} from '@tauri-apps/plugin-dialog';
import type {ProjectState} from '../native';
import {WorkflowController} from './controller';
import {LocalWorkflowPanel} from './LocalWorkflowPanel';
import {connectNativeWorkflow} from './nativePort';

// UI remount does not erase a draft, pending owner IDs or the native session.
let retained: {scope: string; controller: WorkflowController} | null = null;
export function NativeWorkflowPanel({project}: {project: ProjectState | null}) {
  const [controller, setController] = useState<WorkflowController | null>(null);
  const [message, setMessage] = useState('正在读取本地工作流宿主。');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    void connectNativeWorkflow().then(port => {
      if (!active) return;
      if (!retained || retained.scope !== port.scope_id) {
        retained?.controller.dispose();
        retained = {scope: port.scope_id, controller: new WorkflowController(port)};
      }
      setController(retained.controller);
    }, error => { if (active) setMessage(error instanceof Error ? error.message : String(error)); });
    return () => { active = false; };
  }, [attempt]);
  if (!controller) return <section><h3>本地自动化工作流</h3><p role="status">{message}</p>
    <button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取工作流宿主</button></section>;
  return <Connected controller={controller} project={project}/>;
}
function Connected({controller, project}: {controller: WorkflowController; project: ProjectState | null}) {
  useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);
  const [error, setError] = useState('');
  async function directory(kind: 'directory_source' | 'managed_import' | 'export') {
    const before = controller.getState().draft.graph;
    try {
      const selected = await open({directory: true, multiple: false, title: '选择已有本地目录'});
      const current = controller.getState().draft.graph;
      if (typeof selected !== 'string' || controller.editingLocked || current.workflow_id !== before.workflow_id || current.revision !== before.revision) return;
      controller.updateDraft(value => ({...value, graph: {...value.graph, nodes: value.graph.nodes.map(node => {
        if (node.operation.kind !== kind) return node;
        if (node.operation.kind === 'directory_source') return {...node, operation: {...node.operation, root: selected}};
        if (node.operation.kind === 'managed_import') return {...node, operation: {...node.operation, managed_root: selected}};
        if (node.operation.kind === 'export') return {...node, operation: {...node.operation, output_root: selected}};
        return node;
      })}}));
      setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }
  return <>
    <fieldset disabled={controller.editingLocked}><legend>使用实际工程与目录填写草稿</legend>
      <button type="button" disabled={!project?.open || !project.project_id || !project.path || !!project.dirty}
        onClick={() => controller.updateDraft(value => ({...value, graph: {...value.graph, nodes: value.graph.nodes.map(node =>
          node.operation.kind === 'managed_import' ? {...node, operation: {...node.operation, project_id: project?.project_id ?? '', project_path: project?.path ?? ''}} : node)}}))}>填入当前已保存工程</button>
      <button type="button" onClick={() => void directory('directory_source')}>选择来源目录</button>
      <button type="button" onClick={() => void directory('managed_import')}>选择托管目录</button>
      <button type="button" onClick={() => void directory('export')}>选择导出目录</button>
      <p>只填写草稿，不保存、不开始处理。仍需保存、取得独占租约并检测全部节点。</p>
      {error && <p role="alert">{error}</p>}
    </fieldset>
    <LocalWorkflowPanel controller={controller}/>
  </>;
}
