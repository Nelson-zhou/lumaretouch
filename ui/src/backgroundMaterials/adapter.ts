import { MaterialError, parseMutation, parsePage, parseSelection, parseSnapshot, parseThumbnail,
  type MaterialCommand, type MaterialMutation, type MaterialPage, type MaterialQuery, type MaterialSelection, type MaterialSnapshot } from './model';

export type RequestOptions = { signal: AbortSignal };
export interface BackgroundMaterialPort {
  snapshot(options: RequestOptions): Promise<MaterialSnapshot>;
  page(query: MaterialQuery, head: MaterialSnapshot, options: RequestOptions): Promise<MaterialPage>;
  command(command: MaterialCommand, head: MaterialSnapshot, options: RequestOptions): Promise<MaterialMutation>;
  select(id: string, head: MaterialSnapshot, options: RequestOptions): Promise<MaterialSelection>;
  thumbnail(id: string, revision: number, options: RequestOptions): Promise<string>;
  chooseImportPaths(kind: 'images' | 'folder', options: RequestOptions): Promise<string[] | null>;
}
export interface BackgroundMaterialBindings {
  snapshot(options: RequestOptions): Promise<unknown>;
  page(query: MaterialQuery, expected_revision: number, options: RequestOptions): Promise<unknown>;
  command(command: MaterialCommand, expected_revision: number, options: RequestOptions): Promise<unknown>;
  select(id: string, expected_revision: number, options: RequestOptions): Promise<unknown>;
  thumbnail(id: string, expected_revision: number, options: RequestOptions): Promise<unknown>;
  chooseImportPaths(kind: 'images' | 'folder', options: RequestOptions): Promise<unknown>;
}
function check(options: RequestOptions) {
  if (options.signal.aborted) throw new MaterialError('操作已取消，尚未提交。', 'cancelled');
}
/** Kept transport-neutral for embedded consumers and synthetic acceptance fixtures. */
export function createBackgroundMaterialPort(bindings: BackgroundMaterialBindings): BackgroundMaterialPort {
  return {
    async snapshot(options) { check(options); const result = parseSnapshot(await bindings.snapshot(options)); check(options); return result; },
    async page(query, head, options) { check(options); const result = parsePage(await bindings.page(query, head.revision, options), query, head); check(options); return result; },
    async command(command, head, options) {
      check(options);
      try { return parseMutation(await bindings.command(command, head.revision, options), head); }
      catch (error) {
        if (error instanceof MaterialError && error.code !== 'invalid_reply') throw error;
        throw new MaterialError(error instanceof Error ? error.message : String(error), 'invalid_reply', 'unknown');
      }
      // A late AbortSignal must not turn an acknowledged commit into a rollback.
    },
    async select(id, head, options) {
      check(options); const selected = parseSelection(await bindings.select(id, head.revision, options));
      if (selected.material_id !== id || selected.library_id !== head.library_id || selected.catalog_revision !== head.revision) throw new MaterialError('所选素材身份或目录版本已经变化。', 'stale_selection');
      check(options); return selected;
    },
    async thumbnail(id, revision, options) { check(options); const result = parseThumbnail(await bindings.thumbnail(id, revision, options), id, revision); check(options); return result; },
    async chooseImportPaths(kind, options) {
      check(options); const paths = await bindings.chooseImportPaths(kind, options); check(options);
      if (paths === null) return null;
      if (!Array.isArray(paths) || paths.length > 1000 || paths.some(path => typeof path !== 'string' || !path || path.includes('\0'))) throw new MaterialError('原生选择器返回了无效路径。', 'invalid_paths');
      return [...new Set(paths as string[])];
    },
  };
}
