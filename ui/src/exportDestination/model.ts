export type DestinationPolicy = {
  mode: 'chosen_root' | 'source_folder'; chosen_root: string | null;
  retain_hierarchy: boolean; source_subfolder: 'none' | 'project' | 'import_root';
  project_name: string; layout_root?: string | null; conflict: 'rename' | 'skip' | 'ask'; create_missing: boolean;
};
export type DestinationEntry = {
  item_id: string; source_path: string; frame_receipt: string; target: string;
  disposition: 'write' | 'skip' | 'needs_confirmation'; renamed_from: string | null;
  missing_directories: string[]; origin_kind?: string;
};
export type DestinationPreview = {
  schema_version: 'lrt.export-destination.v1'; plan_id: string; intent_revision: number;
  entries: DestinationEntry[];
};
export const initialDestination = (): DestinationPolicy => ({
  mode: 'chosen_root', chosen_root: null, retain_hierarchy: false,
  source_subfolder: 'project', project_name: 'Exports', conflict: 'skip', create_missing: false,
});
