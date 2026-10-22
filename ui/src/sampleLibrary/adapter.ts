import {
  PAGE_SIZE, SampleLibraryError, parseMutation, parseReference, parseSnapshot, parsePage, parseReceiptRevision, normalizedName,
  type LibraryMutationResult, type SampleLibraryCommand, type SampleLibrarySnapshot,
  type SampleReference, type SampleSelectionResult, type SamplePageRequest, type SampleLibraryPage,
} from './model';

export interface RequestOptions { signal: AbortSignal }
export interface CaptureContext {
  /** App's current load identity; distinct from canonical DocumentVersions.document_id. */
  load_id: string;
  /** Obtain document_id/revision/key from backend method:'context', never status.doc_rev. */
  /** Changes whenever the source document OR any relevant edit revision changes. */
  key: string;
  document_id: string;
  revision: string;
  label: string;
  available: boolean;
  unavailableReason?: string;
}
export interface CaptureInput {
  name: string;
  group_id: string | null;
  expected_context: { document_id: string; revision: string };
}
export interface CaptureEvidence {
  document_id: string;
  revision: string;
  state_key: string;
  sample_id: string;
  source_kind: 'frozen_render';
  original_resolution: true;
  render_sha256: string;
}
export interface CaptureResult { revision: number; sample_id: string; reference: SampleReference; capture: CaptureEvidence; duplicate?: boolean; archived?: boolean; message?: string }
export interface SampleLibraryPort {
  snapshot(options: RequestOptions): Promise<SampleLibrarySnapshot>;
  page(request: SamplePageRequest, expectedRevision: number, options: RequestOptions): Promise<SampleLibraryPage>;
  command(command: SampleLibraryCommand, expectedRevision: number, options: RequestOptions): Promise<LibraryMutationResult>;
  chooseImportPaths(kind: 'images' | 'folder', options: RequestOptions): Promise<string[] | null>;
  thumbnail(id: string, options: RequestOptions): Promise<string>;
  /** Validates precision support and returns a content-addressed identity, never a thumbnail path. */
  select(id: string, expectedRevision: number, options: RequestOptions): Promise<SampleSelectionResult>;
  /** Optional: only wire when an original-resolution, revision-frozen renderer exists. */
  captureCurrentResult?(input: CaptureInput, expectedRevision: number, options: RequestOptions): Promise<CaptureResult>;
}

/**
 * Native/application composition boundary. This file imports no native commands.
 * The host maps these callbacks to its own IPC names and converts engine errors
 * into SampleLibraryError with an explicit mutationState.
 *
 * A cancelled native write MUST finish as known-not-applied or return the actual
 * committed result. Do not Promise.race a write against AbortSignal and pretend
 * the write was cancelled. Abort before the atomic commit, or report the commit.
 */
export interface SampleLibraryBindings {
  snapshot(options: RequestOptions): Promise<unknown>;
  page(request: SamplePageRequest, expectedRevision: number, options: RequestOptions): Promise<unknown>;
  command(op: SampleLibraryCommand['op'], payload: SampleLibraryCommand['payload'], expectedRevision: number, options: RequestOptions): Promise<unknown>;
  chooseImportPaths(kind: 'images' | 'folder', options: RequestOptions): Promise<readonly string[] | null>;
  thumbnail(id: string, options: RequestOptions): Promise<unknown>;
  select(id: string, expectedRevision: number, options: RequestOptions): Promise<unknown>;
  /**
   * Freeze the stated document/edit identity, render through the full-resolution
   * pipeline, validate the context again, then atomically persist. Never use SHM
   * display pixels, canvas, viewport screenshots or an upscaled preview.
   * Return {revision, sample_id, duplicate?, archived?, capture: CaptureEvidence}. On cancellation after
   * commit return that successful receipt; cancellation never deletes an asset.
   */
  captureCurrentResult?(input: CaptureInput, expectedRevision: number, options: RequestOptions): Promise<unknown>;
}
function checkAbort(options: RequestOptions): void {
  if (options.signal.aborted) throw new DOMException('操作已取消。', 'AbortError');
}
function checkWriteAbort(options: RequestOptions): void {
  if (options.signal.aborted) throw new SampleLibraryError('操作已取消，尚未提交写入。', 'cancelled', 'not-applied');
}
function mutationError(error: unknown): never {
  if (error instanceof SampleLibraryError && error.code !== 'invalid_reply') throw error;
  throw new SampleLibraryError(error instanceof Error ? error.message : String(error), 'outcome_unknown', 'unknown');
}
function verifyRevision(result: { revision: number }, expectedRevision: number): void {
  if (result.revision < expectedRevision) throw new SampleLibraryError('返回了过期的目录版本。', 'invalid_reply', 'unknown');
}
function validThumbnail(value: unknown): string {
  if (typeof value !== 'string' || !/^data:image\/(?:png|jpeg|webp);base64,[a-zA-Z0-9+/=\r\n]+$/.test(value)) {
    throw new SampleLibraryError('缩略图数据无效。', 'invalid_thumbnail');
  }
  return value;
}
export function createSampleLibraryPort(bindings: SampleLibraryBindings): SampleLibraryPort {
  const port: SampleLibraryPort = {
    async snapshot(options) {
      checkAbort(options);
      const result = parseSnapshot(await bindings.snapshot(options));
      checkAbort(options);
      return result;
    },
    async page(request, expectedRevision, options) {
      checkAbort(options);
      if (!Number.isInteger(request.limit) || request.limit < 1 || request.limit > PAGE_SIZE) {
        throw new SampleLibraryError('元数据分页容量无效。', 'invalid_query');
      }
      const result = parsePage(await bindings.page(request, expectedRevision, options), request, expectedRevision);
      checkAbort(options);
      return result;
    },
    async command(command, expectedRevision, options) {
      checkWriteAbort(options);
      try {
        const result = parseMutation(await bindings.command(command.op, command.payload, expectedRevision, options));
        // A committed receipt must survive a late AbortSignal so callers can reconcile.
        verifyRevision(result, expectedRevision);
        return result;
      } catch (error) { return mutationError(error); }
    },
    async chooseImportPaths(kind, options) {
      checkAbort(options);
      const result = await bindings.chooseImportPaths(kind, options);
      checkAbort(options);
      if (result === null) return null;
      if (!Array.isArray(result) || result.some(path => typeof path !== 'string' || !path || path.includes('\0'))) {
        throw new SampleLibraryError('原生文件选择器未返回有效路径。', 'invalid_paths');
      }
      return [...new Set(result)];
    },
    async thumbnail(id, options) {
      checkAbort(options);
      const result = validThumbnail(await bindings.thumbnail(id, options));
      checkAbort(options);
      return result;
    },
    async select(id, expectedRevision, options) {
      checkWriteAbort(options);
      try {
        const raw = await bindings.select(id, expectedRevision, options);
        const revision = parseReceiptRevision(raw);
        verifyRevision({ revision }, expectedRevision);
        const receipt = raw as { sample_id?: unknown; reference?: unknown; notice?: unknown; snapshot?: unknown };
        if (!receipt || receipt.sample_id !== id || receipt.snapshot !== undefined) {
          throw new SampleLibraryError('参考样片身份或分页回执无效。', 'invalid_reply', 'unknown');
        }
        const reference = parseReference(receipt.reference);
        return { revision, sample_id: id, reference, ...(typeof receipt.notice === 'string' ? { notice: receipt.notice } : {}) };
      } catch (error) { return mutationError(error); }
    },
  };
  if (bindings.captureCurrentResult) {
    const capture = bindings.captureCurrentResult;
    port.captureCurrentResult = async (input, expectedRevision, options) => {
      checkWriteAbort(options);
      const name = normalizedName(input.name);
      try {
        const raw = await capture({ ...input, name }, expectedRevision, options);
        const revision = parseReceiptRevision(raw);
        verifyRevision({ revision }, expectedRevision);
        const proof = raw && typeof raw === 'object' ? (raw as { capture?: Partial<CaptureEvidence> }).capture : undefined;
        if (!proof || proof.document_id !== input.expected_context.document_id || proof.revision !== input.expected_context.revision ||
          typeof proof.state_key !== 'string' || !proof.state_key || proof.source_kind !== 'frozen_render' || proof.original_resolution !== true ||
          typeof proof.sample_id !== 'string' || typeof proof.render_sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(proof.render_sha256)) {
          throw new SampleLibraryError('缺少原尺寸冻结成片的保存凭据，请核对目录。', 'invalid_reply', 'unknown');
        }
        const extras = raw as { reference?: unknown; sample_id?: unknown; duplicate?: unknown; archived?: unknown; message?: unknown; snapshot?: unknown };
        const reference = parseReference(extras.reference);
        if (extras.sample_id !== proof.sample_id || extras.snapshot !== undefined || reference.render_sha256 !== proof.render_sha256) {
          throw new SampleLibraryError('保存回执的样片身份或分页格式无效。', 'invalid_reply', 'unknown');
        }
        return { revision, sample_id: proof.sample_id, reference, capture: proof as CaptureEvidence, duplicate: extras.duplicate === true,
          ...(typeof extras.archived === 'boolean' ? { archived: extras.archived } : {}),
          ...(typeof extras.message === 'string' ? { message: extras.message } : {}) };
      } catch (error) { return mutationError(error); }
    };
  }
  return port;
}
