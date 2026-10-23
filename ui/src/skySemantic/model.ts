export type Region = 'sky' | 'person' | 'water';
export const REGIONS: Region[] = ['sky', 'person', 'water'];
export const LABEL: Record<Region, string> = {sky: '天空', person: '人物保护', water: '水面'};
export interface SemanticDescriptor {
  version: 1; domain: 'source-normalized'; source: {sha256: string; width: number; height: number};
  model: Record<string, string>; host: Record<string, string>; device: 'cpu' | 'cuda';
  input_sha256: string; input_size: [number, number]; fields_sha256: Record<Region, string>;
  regions: Partial<Record<Region, number>>;
}
export interface Proposal {
  event: 'sky_semantic_proposal'; proposal_id: string; state: 'running' | 'ready' | 'failed' | 'cancelled';
  error?: string; source_image?: string; candidate_overlays?: Record<Region, string>; counts?: Record<Region, number>;
  proposal_only?: boolean; review_required?: boolean; horizon_automatic?: false;
}
export interface InstallStatus {
  running: boolean; action?: 'idle' | 'status' | 'install' | 'migrate'; error?: string | null;
  result: {state: string; phase?: string; installed?: boolean; error?: string; reason?: string; received?: number; total?: number;
    download_bytes?: number; weight_bytes?: number; license?: string; license_url?: string;
    migration_available?: boolean; migration_bytes?: number; migration_source_identity?: Record<string, string>;
    migration_reason?: string; migrated?: boolean; requires_descriptor_review?: boolean; publication_warning?: string;
    runtime?: {name: string; version: string; license: string; source: string}[]};
}
export interface SemanticPorts {
  model(action: 'status' | 'install' | 'migrate' | 'cancel'): Promise<InstallStatus>;
  pollModel(): Promise<InstallStatus>;
  start(device: 'cpu' | 'cuda'): Promise<{proposal_id: string}>;
  cancel(): Promise<unknown>;
  shown(proposal: string, region: Region): Promise<unknown>;
  accept(proposal: string, regions: Partial<Record<Region, number>>): Promise<{
    semantic: SemanticDescriptor; draft_only: true; requires_sky_output_review: true;
  }>;
  listen(handler: (event: Proposal) => void): Promise<() => void>;
}
