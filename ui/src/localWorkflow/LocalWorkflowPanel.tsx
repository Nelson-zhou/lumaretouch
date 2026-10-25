import {PresetHandoffPanel} from './PresetHandoffPanel';
import {WorkflowPresetPicker, type PresetCatalogue} from './presetCatalogue';
// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState, useSyncExternalStore} from 'react';
import type {ErrorPolicy, NodeKind, WorkflowCapabilities, WorkflowDiagnostic, WorkflowGraph, WorkflowNode,
  WorkflowOperation, WorkflowRun} from './contracts';
import {WorkflowController} from './controller';
import {edgeProblem, leaseMatches, MAX_NODES, newOperation, NODE_LABELS, POLICY_LABELS, validateGraph} from './model';
import './localWorkflow.css';

const RUN_LABELS = {running: '运行中', paused: '暂停等待处理', stopping: '正在安全停止', stopped: '已停止', complete: '已完成', failed: '失败'};
const STEP_LABELS = {waiting: '等待', running: '处理中', pending: '等待回执', unknown: '结果未知', review_required: '需要人工审核',
  succeeded: '已成功', failed: '失败', skipped: '已跳过', stopped: '已停止'};
const splitList = (text: string) => text.trim() ? text.split(',').map(item => item.trim()) : [];

function Diagnostics({items, label}: {items: WorkflowDiagnostic[]; label: string}) {
  return <section className="local-workflow-diagnostics" aria-label={label}>
    <h4>{label}</h4>
    {items.length ? <ul>{items.map((item, index) => <li key={`${item.code}:${index}`} data-severity={item.severity}>
      <strong>{item.severity === 'error' ? '阻止运行' : item.severity === 'warning' ? '注意' : '信息'}</strong>
      {item.node_id && <span> · {item.node_id}</span>}：{item.message}
    </li>)}</ul> : <p>未发现本层诊断。仍需宿主检测真实目录、工程、预设和导出能力。</p>}
  </section>;
}

function NodeParameters({operation: op, onChange, catalogue}: {operation: WorkflowOperation; catalogue: PresetCatalogue | null; onChange: (op: WorkflowOperation) => void}) {
  switch (op.kind) {
    case 'directory_source': return <>
      <label>来源文件夹（绝对路径）<input value={op.root} placeholder="/photos/incoming" onChange={event => onChange({...op, root: event.currentTarget.value})}/></label>
      <div className="local-workflow-checks">
        <label><input type="checkbox" checked={op.recursive} onChange={event => onChange({...op, recursive: event.currentTarget.checked})}/>包含子文件夹</label>
        <label><input type="checkbox" checked={op.include_existing} onChange={event => onChange({...op, include_existing: event.currentTarget.checked})}/>首次启动也处理已有照片</label>
      </div>
      <label>扩展名（逗号分隔，不含点）<input value={op.extensions.join(',')} onChange={event => onChange({...op, extensions: splitList(event.currentTarget.value)})}/></label>
      <label>文件稳定等待（毫秒）<input type="number" min={250} max={300000} step={1} value={op.settle_ms}
        onChange={event => onChange({...op, settle_ms: Number(event.currentTarget.value)})}/></label>
      <small>默认只接收启动后的新照片。文件稳定且通过宿主核验后才处理，不跟随不安全的路径别名。</small>
    </>;
    case 'managed_import': return <>
      <label>当前已加载工程标识<input value={op.project_id} onChange={event => onChange({...op, project_id: event.currentTarget.value})}/></label>
      <label>工程文件（绝对路径）<input value={op.project_path} onChange={event => onChange({...op, project_path: event.currentTarget.value})}/></label>
      <label>托管原图文件夹（绝对路径）<input value={op.managed_root} onChange={event => onChange({...op, managed_root: event.currentTarget.value})}/></label>
      <small>必须是当前已加载、已保存且无未保存修改的工程。取得工作流独占租约期间暂停交互编辑；不会自动保存、打开或切换工程。</small>
    </>;
    case 'path_labels': return <>
      <p>仅按文件名或相对路径的包含关系添加标签，区分大小写，不进行 AI 选片。</p>
      {op.rules.map((rule, index) => <div className="local-workflow-rule" key={index}>
        <label>匹配范围<select value={rule.target} onChange={event => onChange({...op, rules: op.rules.map((item, i) => i === index ?
          {...item, target: event.currentTarget.value as 'filename' | 'relative_path'} : item)})}>
          <option value="filename">文件名</option><option value="relative_path">相对路径</option></select></label>
        <label>包含文本<input value={rule.contains} onChange={event => onChange({...op, rules: op.rules.map((item, i) => i === index ? {...item, contains: event.currentTarget.value} : item)})}/></label>
        <label>添加标签<input value={rule.label} onChange={event => onChange({...op, rules: op.rules.map((item, i) => i === index ? {...item, label: event.currentTarget.value} : item)})}/></label>
        <button type="button" onClick={() => onChange({...op, rules: op.rules.filter((_, i) => i !== index)})}>删除规则 {index + 1}</button>
      </div>)}
      <button type="button" disabled={op.rules.length >= 64} onClick={() => onChange({...op, rules: [...op.rules, {target: 'filename', contains: '', label: ''}]})}>添加标签规则</button>
    </>;
    case 'compatible_preset': return <>
      <WorkflowPresetPicker catalogue={catalogue} operation={op} onChange={onChange}/>
      <label>必须同时具备的标签（逗号分隔；留空匹配全部）<input value={op.when_all_labels.join(',')} onChange={event => onChange({...op, when_all_labels: splitList(event.currentTarget.value)})}/></label>
      <small>宿主按真实预设内容检查兼容性。需要逐图审核的效果会暂停，只有原审核流程产生的有效回执才能继续。</small>
    </>;
    case 'export': return <>
      <label>导出文件夹（绝对路径）<input value={op.output_root} onChange={event => onChange({...op, output_root: event.currentTarget.value})}/></label>
      <label>导出配方 SHA-256 指纹<input value={op.recipe_sha256} maxLength={64} spellCheck={false} onChange={event => onChange({...op, recipe_sha256: event.currentTarget.value})}/></label>
      <small>使用宿主已保存并核验的导出配方。导出目录不能与来源或托管原图目录重叠；不覆盖原片。</small>
    </>;
  }
}

function NodeCard({node, locked, capabilities, onChange, onRemove, catalogue}: {node: WorkflowNode; locked: boolean;
  capabilities: WorkflowCapabilities | null; catalogue: PresetCatalogue | null; onChange: (node: WorkflowNode) => void; onRemove: () => void}) {
  const supported = capabilities?.error_policies[node.operation.kind] ?? [];
  return <fieldset className="local-workflow-node" disabled={locked}>
    <legend>{NODE_LABELS[node.operation.kind]} · {node.id}</legend>
    <NodeParameters catalogue={catalogue} operation={node.operation} onChange={operation => onChange({...node, operation})}/>
    <label>错误策略<select value={node.error_policy} onChange={event => onChange({...node, error_policy: event.currentTarget.value as ErrorPolicy})}>
      {(Object.keys(POLICY_LABELS) as ErrorPolicy[]).map(policy => <option key={policy} value={policy}
        disabled={!supported.includes(policy) || (policy === 'keep_continue' && node.operation.kind !== 'compatible_preset') || (node.operation.kind === 'directory_source' && policy !== 'stop')}>
        {POLICY_LABELS[policy]}{!supported.includes(policy) ? '（宿主未确认支持）' : ''}
      </option>)}
    </select></label>
    {node.error_policy === 'keep_continue' && <small>仅在宿主确认失败结果已定、工程未改变且仍可用时继续。未知回执和人工审核绝不能跳过。</small>}
    <button type="button" className="local-workflow-subtle" onClick={onRemove}>删除节点及关联连线</button>
  </fieldset>;
}

function EdgeEditor({graph, locked, onChange}: {graph: WorkflowGraph; locked: boolean; onChange: (graph: WorkflowGraph) => void}) {
  const [from, setFrom] = useState(''), [to, setTo] = useState('');
  const selectedFrom = graph.nodes.some(node => node.id === from) ? from : '';
  const selectedTo = graph.nodes.some(node => node.id === to) ? to : '';
  const problem = selectedFrom && selectedTo ? edgeProblem(graph, {from: selectedFrom, to: selectedTo}) : '请选择连线的起点和终点。';
  return <fieldset disabled={locked} className="local-workflow-edges">
    <legend>编辑连线</legend>
    <p>本地 v1 为单链：来源 → 导入 → 可选标签 → 可选预设 → 导出。新增节点后，请手动调整连线。</p>
    <ul>{graph.edges.map((edge, index) => <li key={`${edge.from}:${edge.to}:${index}`}>
      <span>{edge.from} → {edge.to}</span>
      <button type="button" onClick={() => onChange({...graph, edges: graph.edges.filter((_, i) => i !== index)})}>移除连线</button>
    </li>)}</ul>
    <div className="local-workflow-inline">
      <label>起点<select value={selectedFrom} onChange={event => setFrom(event.currentTarget.value)}><option value="">选择节点</option>
        {graph.nodes.map(node => <option key={node.id} value={node.id} disabled={node.operation.kind === 'export'}>{NODE_LABELS[node.operation.kind]} · {node.id}</option>)}
      </select></label>
      <label>终点<select value={selectedTo} onChange={event => setTo(event.currentTarget.value)}><option value="">选择节点</option>
        {graph.nodes.map(node => <option key={node.id} value={node.id} disabled={node.operation.kind === 'directory_source'}>{NODE_LABELS[node.operation.kind]} · {node.id}</option>)}
      </select></label>
      <button type="button" disabled={!!problem} onClick={() => {if (!problem) onChange({...graph, edges: [...graph.edges, {from: selectedFrom, to: selectedTo}]});}}>添加连线</button>
    </div>
    {problem && <small>{problem}</small>}
  </fieldset>;
}

function RunDetails({run}: {run: WorkflowRun}) {
  return <section className="local-workflow-run" aria-label="逐文件和节点运行结果">
    <h4>{RUN_LABELS[run.status]} · {run.completed_files} / {run.total_files} 张</h4>
    <p>运行 {run.run_id} · 图修订 {run.graph_revision} · 状态序号 {run.sequence}</p>
    {run.effects_settled !== true && ['stopped', 'complete', 'failed'].includes(run.status) &&
      <p className="local-workflow-warning">派发已结束，但已有操作的结果尚未全部核实。继续查询原回执，工程与图配置保持锁定。</p>}
    {run.review && <p className="local-workflow-warning">等待真实人工审核：{run.review.family} · {run.review.reason}</p>}
    {run.diagnostics.length > 0 && <Diagnostics label="运行诊断" items={run.diagnostics}/>}
    {run.files.length === 0 && <p>宿主尚未返回文件记录。开启监听不代表已有照片处理成功。</p>}
    {run.records_truncated && <p>当前仅显示宿主返回的一部分记录；总数以运行汇总为准。</p>}
    <ol className="local-workflow-files">{run.files.map(file => <li key={file.file_id}>
      <details><summary>{file.relative_path} · {STEP_LABELS[file.status]} · {file.stage}</summary>
        {file.labels.length > 0 && <p>标签：{file.labels.join('、')}</p>}
        {file.message && <p>{file.message}</p>}
        {file.output_path && <p>宿主报告的输出：{file.output_path}</p>}
        <ul>{file.nodes.map(record => <li key={record.node_id}>
          {record.node_id} · {STEP_LABELS[record.status]}{record.message && ` · ${record.message}`}
          {record.receipt_id && <small>操作回执：{record.receipt_id}</small>}
        </li>)}</ul>
      </details>
    </li>)}</ol>
  </section>;
}

export interface LocalWorkflowPanelProps {
  /** Created and retained by the host, not constructed on every render. */
  controller: WorkflowController;
}
export function LocalWorkflowPanel({controller}: LocalWorkflowPanelProps) {
  const state = useSyncExternalStore(controller.subscribe, controller.getState, controller.getState);
  const [selectedDefinition, setSelectedDefinition] = useState('');
  const [replacement, setReplacement] = useState<{kind: 'new'} | {kind: 'load'; workflow_id: string} | null>(null);
  const [addKind, setAddKind] = useState<NodeKind>('path_labels');
  useEffect(() => {
    void controller.refresh();
    const timer = setInterval(() => {void controller.tick();}, 2000);
    return () => {clearInterval(timer);};
  }, [controller]);
  useEffect(() => {setReplacement(null); setSelectedDefinition('');}, [controller]);
  const {draft, capabilities, active_run: activeRun} = state;
  const graph = draft.graph, locked = controller.editingLocked;
  const localDiagnostics = validateGraph(graph, capabilities ?? undefined);
  const hasErrors = localDiagnostics.some(item => item.severity === 'error');
  const leaseValid = leaseMatches(graph, state.lease);
  const changeGraph = (next: WorkflowGraph) => controller.updateDraft(value => ({...value, graph: next}));
  const doReplace = (action: NonNullable<typeof replacement>) => {
    if (action.kind === 'new') controller.newWorkflow(); else void controller.load(action.workflow_id);
    setReplacement(null);
  };
  const requestReplace = (action: NonNullable<typeof replacement>) => {if (state.dirty) setReplacement(action); else doReplace(action);};
  const viewedRun = state.inspected_run && state.inspected_run.run_id !== activeRun?.run_id ? state.inspected_run : activeRun ?? state.inspected_run;
  const supportedNew = !graph.nodes.some(node => node.operation.kind === addKind) && graph.nodes.length < MAX_NODES;
  const exportNode = graph.nodes.find(node => node.operation.kind === 'export')?.operation;
  return <section className="local-workflow" aria-label="本地自动化工作流">
    <header className="local-workflow-heading"><div><h3>本地自动化工作流</h3>
      <p>目录接入、当前已保存工程、可选标签与预设、导出。所有运行结果来自本机宿主。</p></div>
      <span className="local-workflow-badge">{activeRun ? RUN_LABELS[activeRun.status] : state.dirty ? '未保存草稿' : '未运行'}</span>
    </header>
    {(!state.ready || !capabilities?.available) && <p className="local-workflow-warning" role="status">
      {capabilities?.reason ?? (state.busy ? '正在读取宿主及恢复状态…' : '宿主尚未确认可运行。编辑草稿不会启动任务。')}
    </p>}
    <div className="local-workflow-toolbar">
      <button type="button" disabled={locked} onClick={() => requestReplace({kind: 'new'})}>新建工作流</button>
      <label>已保存定义<select disabled={locked} value={selectedDefinition} onChange={event => setSelectedDefinition(event.currentTarget.value)}>
        <option value="">选择已保存的工作流</option>{state.definitions.map(item => <option value={item.workflow_id} key={item.workflow_id}>{item.name}</option>)}
      </select></label>
      <button type="button" disabled={locked || !selectedDefinition} onClick={() => requestReplace({kind: 'load', workflow_id: selectedDefinition})}>加载定义</button>
      <button type="button" disabled={locked || !capabilities?.can_save || !draft.name.trim()} onClick={() => void controller.save()}>保存定义</button>
      <button type="button" disabled={state.busy} onClick={() => void controller.refresh()}>刷新宿主状态</button>
      <button type="button" disabled={state.busy} onClick={() => void controller.refreshCatalogue()}>刷新实际预设目录</button>
    </div>
    {replacement && <div className="local-workflow-warning" role="alert">
      <p>当前草稿尚未保存。继续会替换草稿，不会删除已保存的工作流。</p>
      <button type="button" disabled={locked} onClick={() => doReplace(replacement)}>放弃草稿并继续</button>
      <button type="button" onClick={() => setReplacement(null)}>保留草稿</button>
    </div>}
    <div className="local-workflow-layout"><div>
      <fieldset disabled={locked} className="local-workflow-definition"><legend>工作流定义</legend>
        <label>名称<input value={draft.name} maxLength={120} onChange={event => controller.updateDraft(value => ({...value, name: event.currentTarget.value}))}/></label>
        <label>说明（选填）<textarea value={draft.description} maxLength={2000} onChange={event => controller.updateDraft(value => ({...value, description: event.currentTarget.value}))}/></label>
        <small>标识 {graph.workflow_id} · 图修订 {graph.revision} · {state.dirty ? '存在未保存修改' : `保存版本 ${draft.storage_revision ?? '无'}`}</small>
      </fieldset>
      <div className="local-workflow-inline"><label>节点类型<select disabled={locked} value={addKind} onChange={event => setAddKind(event.currentTarget.value as NodeKind)}>
        {(Object.keys(NODE_LABELS) as NodeKind[]).map(kind => <option value={kind} key={kind} disabled={graph.nodes.some(node => node.operation.kind === kind)}>{NODE_LABELS[kind]}</option>)}
      </select></label>
        <button type="button" disabled={locked || !supportedNew} onClick={() => {
          if (!supportedNew) return;
          let i = 1; while (graph.nodes.some(node => node.id === `node-${i}`)) i += 1;
          changeGraph({...graph, nodes: [...graph.nodes, {id: `node-${i}`, error_policy: 'stop', operation: newOperation(addKind)}]});
        }}>添加节点</button>
      </div>
      <div className="local-workflow-nodes">{graph.nodes.map(node => <NodeCard key={node.id} node={node} locked={locked} capabilities={capabilities} catalogue={state.preset_catalogue}
        onChange={next => changeGraph({...graph, nodes: graph.nodes.map(item => item.id === node.id ? next : item)})}
        onRemove={() => changeGraph({...graph, nodes: graph.nodes.filter(item => item.id !== node.id), edges: graph.edges.filter(edge => edge.from !== node.id && edge.to !== node.id)})}/>)}</div>
      <EdgeEditor graph={graph} locked={locked} onChange={changeGraph}/>
    </div><aside className="local-workflow-sidebar">
      <section aria-label="宿主实际导出配方"><h4>宿主固定导出配方</h4>
        {state.export_profile ? <>
          <p>以下为引擎实际回读的固定配置，不是通用导出设置，也没有自动应用到工作流。</p>
          <p>{state.export_profile.recipe_profile.export_options.format.toUpperCase()} · 质量 {state.export_profile.recipe_profile.export_options.quality}
            {' · '}{state.export_profile.recipe_profile.export_options.bit_depth} 位 · {state.export_profile.recipe_profile.export_options.output_profile}</p>
          <pre className="local-workflow-profile" aria-label="完整宿主导出配方 JSON">{JSON.stringify(state.export_profile.recipe_profile, null, 2)}</pre>
          <small>SHA-256：{state.export_profile.recipe_sha256}</small>
          <button type="button" disabled={locked || exportNode?.kind !== 'export' || exportNode.recipe_sha256 === state.export_profile.recipe_sha256}
            onClick={() => controller.useReturnedExportProfile()}>使用宿主返回的导出配方</button>
          <small>仅更新草稿中的真实指纹，之后须保存并重新检测，不会自动启动。</small>
        </> : <p>{state.profile_pending ? '正在等待引擎返回真实配方…' : '宿主尚未返回可用的真实导出配方。可刷新状态；不会填入猜测的指纹。'}</p>}
      </section>
      <section aria-label="检测与运行"><h4>检测与运行</h4>
        <p>请先自行保存当前工程。工作流只会为当前已加载的干净工程取得独占租约，不会自动保存或切换工程。目录必须已存在且互不包含。</p>
        <button type="button" disabled={locked || !!state.lease || !capabilities?.available || !capabilities.can_run} onClick={() => void controller.acquireLease()}>验证当前工程并取得独占租约</button>
        <button type="button" disabled={!controller.canReleaseLease()} onClick={() => void controller.releaseLease()}>释放工程租约</button>
        {state.lease && <p>持有租约：{state.lease.project_id} · {state.lease.project_path}。只有运行与已有操作均已结束，且无未知回执时才可释放。</p>}
        <p>{leaseValid ? `租约有效至 ${state.lease!.expires_at}` : '尚无匹配的有效工程租约。'}</p>
        <div className="local-workflow-actions">
          <button type="button" disabled={locked || hasErrors || !leaseValid || !capabilities?.available || !capabilities.can_run} onClick={() => void controller.check()}>检测</button>
          <button type="button" disabled={!controller.canStart()} onClick={() => void controller.start()}>开启运行</button>
          <button type="button" disabled={!controller.canStop()} onClick={() => void controller.stop()}>停止运行</button>
        </div>
        <small>停止会等待安全边界；已开始的导入或导出可能完成。结果未知时不会重复写入。</small>
        {state.preflight && <><p>检测有效至 {state.preflight.valid_until}。{state.dirty ? '定义尚未保存，不能启动。' : ''}</p>
          <Diagnostics label="宿主检测结果" items={state.preflight.diagnostics}/></>}
      </section>
      <Diagnostics label="图结构与参数" items={localDiagnostics}/>
      {state.pending.length > 0 && <section className="local-workflow-warning" aria-label="未确认操作">
        <h4>正在等待真实回执</h4><p>不确定不是失败，也不是成功。不能重试写入或修改图。</p>
        <ul>{state.pending.map(item => <li key={item.request_id}>{item.command_kind} · {item.request_id}</li>)}</ul>
        <button type="button" disabled={state.busy} onClick={() => void controller.queryPending()}>查询原操作</button>
      </section>}
      <PresetHandoffPanel controller={controller} state={state}/>
      {activeRun?.review && !activeRun.handoff && <section className="local-workflow-warning" aria-label="人工审核暂停">
        <h4>人工审核暂停</h4><p>{activeRun.review.reason}</p>
        <p>{activeRun.review.family} · 文件 {activeRun.review.file_id} · 节点 {activeRun.review.node_id}</p>
        <button type="button" disabled={state.busy || state.pending.length > 0 || !capabilities?.can_open_review || activeRun.status !== 'paused'} onClick={() => void controller.openReview()}>打开真实审核</button>
        <small>这里没有“全部确认”或自动批准。原审核界面完成后，宿主核验对应文件、工程版本和审核回执。</small>
        {!capabilities?.can_open_review && <p>宿主没有提供审核入口，运行会保持暂停；可停止后处理。</p>}
      </section>}
      <section aria-label="保存的运行记录"><h4>运行记录</h4>
        {state.runs.length === 0 && <p>尚未读取到保存的运行记录。</p>}
        <ul>{state.runs.map(run => <li key={run.run_id}>
          <button type="button" disabled={state.busy} onClick={() => void controller.inspectRun(run.run_id)}>{RUN_LABELS[run.status]} · {run.started_at}</button>
          <small>{run.completed_files} / {run.total_files} 张 · {run.run_id}</small>
        </li>)}</ul>
        {state.inspected_run && <button type="button" onClick={() => controller.clearInspection()}>返回当前运行</button>}
      </section>
    </aside></div>
    {state.message && <p role="status" className="local-workflow-message">{state.message}</p>}
    {state.error && <p role="alert" className="local-workflow-error">{state.error}</p>}
    {viewedRun && <RunDetails run={viewedRun}/>}
    <footer>本阶段不包含 ERP、网络下载、任意脚本、AI 选片或循环分支。未接入的能力不会显示为运行成功。</footer>
  </section>;
}
