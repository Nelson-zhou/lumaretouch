// SPDX-License-Identifier: GPL-3.0-or-later
import type {NodeKind, ProjectLease, WorkflowCapabilities, WorkflowDefinition, WorkflowDiagnostic, WorkflowEdge,
  WorkflowGraph, WorkflowNode, WorkflowOperation, WorkflowRun} from './contracts';

export const NODE_LABELS: Record<NodeKind, string> = {
  directory_source: '本地文件夹来源', managed_import: '导入当前工程', path_labels: '文件名 / 路径标签',
  compatible_preset: '兼容预设', export: '导出图片',
};
export const POLICY_LABELS = {stop: '失败中止', skip: '跳过继续', keep_continue: '保留继续'} as const;
export const MAX_NODES = 5;
const HASH = /^[a-f\d]{64}$/;
const ID = /^[a-z\d._:-]{1,128}$/i;
const boundedText = (value: string, maximum: number) => !!value && !/[\u0000-\u001f\u007f]/.test(value) && new TextEncoder().encode(value).length <= maximum;

export function newOperation(kind: NodeKind): WorkflowOperation {
  switch (kind) {
    case 'directory_source': return {kind, root: '', recursive: true, include_existing: false, extensions: ['jpg', 'jpeg', 'png', 'tif', 'tiff'], settle_ms: 2000};
    case 'managed_import': return {kind, project_id: '', project_path: '', managed_root: ''};
    case 'path_labels': return {kind, rules: []};
    case 'compatible_preset': return {kind, preset_id: '', preset_sha256: '', when_all_labels: []};
    case 'export': return {kind, output_root: '', recipe_sha256: ''};
  }
}
export function newDefinition(id: string): WorkflowDefinition {
  const kinds: NodeKind[] = ['directory_source', 'managed_import', 'export'];
  const nodes = kinds.map((kind, i): WorkflowNode => ({id: `node-${i + 1}`, error_policy: 'stop', operation: newOperation(kind)}));
  return {name: '本地修图工作流', description: '', storage_revision: null,
    graph: {schema_version: 1, workflow_id: id, revision: 1, nodes, edges: nodes.slice(1).map((node, i) => ({from: nodes[i].id, to: node.id}))}};
}

/** Conservative lexical check only. Realpath, symlink aliases and volume case rules belong to host preflight. */
function normalizedAbsolutePath(raw: string): string | null {
  const input = raw.replaceAll('\\', '/');
  if (!input.startsWith('/') && !/^[a-z]:\//i.test(input)) return null;
  const prefix = /^[a-z]:\//i.test(input) ? input.slice(0, 2).toLowerCase() : input.startsWith('//') ? '//' : '/';
  const rest = prefix.length === 2 && prefix !== '//' ? input.slice(3) : input.slice(prefix.length);
  const parts: string[] = [];
  for (const part of rest.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') parts.pop(); else parts.push(part);
  }
  const path = prefix === '/' ? `/${parts.join('/')}` : prefix === '//' ? `//${parts.join('/')}` : `${prefix}/${parts.join('/')}`;
  return prefix === '/' ? path : path.toLowerCase();
}
export function pathsOverlap(a: string, b: string): boolean {
  const x = normalizedAbsolutePath(a), y = normalizedAbsolutePath(b);
  if (!x || !y) return false;
  return x === y || x.startsWith(y.endsWith('/') ? y : `${y}/`) || y.startsWith(x.endsWith('/') ? x : `${x}/`);
}
export function edgeProblem(graph: WorkflowGraph, edge: WorkflowEdge): string | null {
  const from = graph.nodes.find(node => node.id === edge.from), to = graph.nodes.find(node => node.id === edge.to);
  if (!from || !to) return '连线两端必须是现有节点。';
  if (from.id === to.id) return '不能连接节点自身。';
  if (from.operation.kind === 'export') return '导出节点没有输出端。';
  if (to.operation.kind === 'directory_source') return '来源节点没有输入端。';
  if (graph.edges.some(item => item.from === edge.from && item.to === edge.to)) return '这条连线已存在。';
  if (graph.edges.some(item => item.from === edge.from || item.to === edge.to)) return '本地 v1 只支持单链，不支持分支或合流。';
  const reachable = new Set<string>();
  const queue = [edge.to];
  while (queue.length) {
    const id = queue.pop()!;
    if (id === edge.from) return '不能形成循环。';
    if (reachable.has(id)) continue;
    reachable.add(id);
    graph.edges.filter(item => item.from === id).forEach(item => queue.push(item.to));
  }
  return null;
}
export function validateGraph(graph: WorkflowGraph, capabilities?: WorkflowCapabilities): WorkflowDiagnostic[] {
  const result: WorkflowDiagnostic[] = [];
  const error = (code: string, message: string, node_id?: string) => result.push({severity: 'error', code, message, node_id});
  if (graph.schema_version !== 1 || !ID.test(graph.workflow_id) || !Number.isSafeInteger(graph.revision) || graph.revision < 1)
    error('graph_identity', '工作流版本、标识或修订号无效。');
  if (graph.nodes.length < 3 || graph.nodes.length > MAX_NODES) error('node_count', '需要来源、导入、导出，可各增加一个标签或预设节点。');
  if (new Set(graph.nodes.map(node => node.id)).size !== graph.nodes.length || graph.nodes.some(node => !ID.test(node.id)))
    error('node_id', '节点标识不能为空或重复。');
  const kinds: NodeKind[] = ['directory_source', 'managed_import', 'export'];
  for (const kind of kinds) if (graph.nodes.filter(node => node.operation.kind === kind).length !== 1)
    error('required_node', `${NODE_LABELS[kind]}必须有且只有一个。`);
  if (graph.nodes.filter(node => node.operation.kind === 'path_labels').length > 1) error('labels_count', '最多支持一个标签节点。');
  if (graph.nodes.filter(node => node.operation.kind === 'compatible_preset').length > 1) error('preset_count', '最多支持一个兼容预设节点。');
  const partial = {...graph, edges: [] as WorkflowEdge[]};
  for (const edge of graph.edges) {
    const problem = edgeProblem(partial, edge);
    if (problem) error('invalid_edge', `${edge.from} → ${edge.to}：${problem}`);
    partial.edges.push(edge);
  }
  const source = graph.nodes.find(node => node.operation.kind === 'directory_source');
  const ordered: NodeKind[] = [], visited = new Set<string>();
  let current = source;
  while (current && !visited.has(current.id)) {
    visited.add(current.id); ordered.push(current.operation.kind);
    const edge = graph.edges.find(item => item.from === current!.id);
    current = edge ? graph.nodes.find(node => node.id === edge.to) : undefined;
  }
  const expected = ['directory_source', 'managed_import',
    ...(graph.nodes.some(node => node.operation.kind === 'path_labels') ? ['path_labels'] : []),
    ...(graph.nodes.some(node => node.operation.kind === 'compatible_preset') ? ['compatible_preset'] : []), 'export'];
  if (visited.size !== graph.nodes.length || ordered.join(',') !== expected.join(',') || graph.edges.length !== graph.nodes.length - 1)
    error('chain', '请连接为：来源 → 导入 → 可选标签 → 可选兼容预设 → 导出。');
  const requirePath = (value: string, label: string, id: string) => {
    if (!normalizedAbsolutePath(value) || !boundedText(value, 4096) || value.replaceAll('\\', '/').split('/').some(part => part === '.' || part === '..'))
      error('absolute_path', `${label}需要规范的本机绝对路径，不能包含 . 或 .. 路径段。`, id);
  };
  for (const node of graph.nodes) {
    if (capabilities && !capabilities.error_policies[node.operation.kind]?.includes(node.error_policy))
      error('policy_unavailable', '宿主没有确认支持该节点的错误策略。', node.id);
    if (node.error_policy === 'keep_continue' && node.operation.kind !== 'compatible_preset')
      error('keep_not_supported', '保留继续仅可用于宿主支持的兼容预设节点。', node.id);
    if (node.operation.kind === 'directory_source' && node.error_policy !== 'stop')
      error('source_must_stop', '目录发现失败必须中止，不能静默丢失输入。', node.id);
    const op = node.operation;
    switch (op.kind) {
      case 'directory_source':
        requirePath(op.root, '来源目录', node.id);
        if (!Number.isSafeInteger(op.settle_ms) || op.settle_ms < 250 || op.settle_ms > 300000) error('settle', '稳定等待时间应为 250–300000 毫秒。', node.id);
        if (!op.extensions.length || op.extensions.length > 32 || new Set(op.extensions).size !== op.extensions.length || op.extensions.some(ext => !/^[a-z\d]{1,10}$/.test(ext)))
          error('extensions', '需要 1–32 个唯一的小写扩展名，每项不超过 10 个字母或数字，不含点号。', node.id);
        break;
      case 'managed_import':
        if (!ID.test(op.project_id)) error('project_id', '请填写当前已保存工程标识（1–128 个字母、数字或 . _ : -）。', node.id);
        requirePath(op.project_path, '工程文件', node.id); requirePath(op.managed_root, '托管原图目录', node.id); break;
      case 'path_labels':
        if (!op.rules.length || op.rules.length > 64 || op.rules.some(rule => !boundedText(rule.contains, 256) || !boundedText(rule.label, 128)))
          error('label_rule', '需要 1–64 条规则；包含文本最多 256 字节，标签最多 128 字节且不能为空。', node.id); break;
      case 'compatible_preset':
        if (!ID.test(op.preset_id) || !HASH.test(op.preset_sha256)) error('preset', '需要有效预设标识和真实的小写 SHA-256 指纹。', node.id);
        if (op.when_all_labels.length > 64 || new Set(op.when_all_labels).size !== op.when_all_labels.length || op.when_all_labels.some(label => !boundedText(label, 128)))
          error('preset_labels', '预设匹配标签最多 64 个，不能重复或为空。', node.id);
        {const known = new Set(graph.nodes.flatMap(item => item.operation.kind === 'path_labels' ? item.operation.rules.map(rule => rule.label) : []));
          if (op.when_all_labels.some(label => !known.has(label))) error('unknown_label', '预设条件引用了标签规则无法产生的标签。', node.id);}
        break;
      case 'export':
        requirePath(op.output_root, '导出目录', node.id);
        if (!HASH.test(op.recipe_sha256)) error('recipe', '需要已核验导出配方的 SHA-256 指纹。', node.id); break;
    }
  }
  const input = source?.operation;
  const output = graph.nodes.find(node => node.operation.kind === 'export')?.operation;
  const imported = graph.nodes.find(node => node.operation.kind === 'managed_import')?.operation;
  if (input?.kind === 'directory_source' && output?.kind === 'export' && pathsOverlap(input.root, output.output_root))
    error('source_export_overlap', '来源与导出目录不能相同，也不能互相包含。');
  if (input?.kind === 'directory_source' && imported?.kind === 'managed_import' && pathsOverlap(input.root, imported.managed_root))
    error('source_managed_overlap', '托管原图目录不能与来源目录重叠，以免重复导入。');
  if (output?.kind === 'export' && imported?.kind === 'managed_import' && pathsOverlap(output.output_root, imported.managed_root))
    error('managed_export_overlap', '托管原图目录与导出目录不能重叠。');
  if (imported?.kind === 'managed_import') {
    const roots = [imported.managed_root, ...(input?.kind === 'directory_source' ? [input.root] : []), ...(output?.kind === 'export' ? [output.output_root] : [])];
    if (roots.some(root => pathsOverlap(root, imported.project_path))) error('project_inside_root', '工程文件不能放在来源、托管原图或导出目录内。');
  }
  if (new TextEncoder().encode(JSON.stringify(graph)).length > 256 * 1024) error('graph_size', '工作流定义不能超过 256 KiB。');
  return result;
}
export function isRunActive(run: WorkflowRun | null): boolean {
  return !!run && (['running', 'paused', 'stopping'].includes(run.status) || run.effects_settled !== true);
}
export function leaseMatches(graph: WorkflowGraph, lease: ProjectLease | null, now = Date.now()): boolean {
  const imported = graph.nodes.find(node => node.operation.kind === 'managed_import')?.operation;
  return imported?.kind === 'managed_import' && !!lease && lease.saved === true && lease.dedicated === true &&
    !!lease.lease_id && lease.project_id === imported.project_id && lease.project_path === imported.project_path &&
    Number.isFinite(Date.parse(lease.expires_at)) && Date.parse(lease.expires_at) > now;
}
