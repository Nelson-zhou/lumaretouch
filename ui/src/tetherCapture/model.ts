// SPDX-License-Identifier: GPL-3.0-or-later
import type {TetherDevice, TetherImportFormat, TetherIngestionTarget, TetherNaming, TetherNamingMode, TetherRecordingFormat, TetherSession, TetherTransfer} from './protocol';

export const IMPORT_FORMATS: ReadonlyArray<{value: TetherImportFormat; label: string}> = [
  {value: 'raw_jpeg', label: 'RAW 和 JPEG'}, {value: 'raw', label: '仅 RAW'}, {value: 'jpeg', label: '仅 JPEG'},
];
export const NAMING_MODES: ReadonlyArray<{value: TetherNamingMode; label: string}> = [
  {value: 'custom_counter', label: '自定义名称-计数器'}, {value: 'custom_filename', label: '自定义名称-文件名称'},
  {value: 'date_counter', label: '日期-计数器'}, {value: 'date_filename', label: '日期-文件名称'},
  {value: 'original', label: '文件名称'},
];
export function permittedFormats(format: TetherRecordingFormat): ReadonlyArray<TetherImportFormat> {
  return format === 'raw_jpeg' ? ['raw_jpeg', 'raw', 'jpeg'] : format === 'raw' ? ['raw'] : format === 'jpeg' ? ['jpeg'] : ['raw_jpeg'];
}
export function defaultImportFormat(format: TetherRecordingFormat): TetherImportFormat {
  return format === 'unknown' ? 'raw_jpeg' : format;
}
export function namingError(naming: TetherNaming): string | null {
  if (!NAMING_MODES.some(item => item.value === naming.mode)) return '命名方式无效。';
  if (naming.mode.startsWith('custom_') && (!naming.custom_name.trim() || /[<>:"/\\|?*\x00-\x1f]/.test(naming.custom_name) || /[. ]$/.test(naming.custom_name) || naming.custom_name.length > 80)) {
    return '请输入 1–80 字符的名称，不含路径分隔符或特殊文件名字符，且不以空格或句点结尾。';
  }
  if (naming.mode.endsWith('_counter') && (!Number.isSafeInteger(naming.counter_start) || naming.counter_start < 1 || naming.counter_start > 999999999)) return '计数器必须为 1–999999999 的整数。';
  return null;
}
export function sessionIsOpen(session: TetherSession | null): boolean {
  return !!session && session.phase !== 'stopped';
}
export function ingestionTargetBlocker(target: TetherIngestionTarget | null | undefined): string | null {
  if (!target?.project_id || !target.path) return '请先打开并保存明确的目标项目，不会默认导入到任意当前项目。';
  if (!target.available) return target.reason || '目标项目尚未取得引擎导入许可。';
  if (!Number.isSafeInteger(target.remaining_operations) || target.remaining_operations <= 0) return '目标项目的导入操作额度不足，请先重新取得导入许可。';
  return null;
}
export function deviceStartBlocker(device: TetherDevice | undefined): string | null {
  if (!device) return '请选择当前运行时实际检测到的相机。';
  if (!device.connected || !device.detected_by_runtime) return '相机未连接，或尚未由当前运行时验证。';
  if (device.capabilities.event_polling.state !== 'verified') return device.capabilities.event_polling.reason || '尚未验证设备事件读取能力。';
  if (device.capabilities.original_download.state === 'unsupported') return device.capabilities.original_download.reason || '此设备不支持原片下载。';
  return null;
}
export function transferCanRetry(transfer: TetherTransfer, session: TetherSession | null): boolean {
  return transfer.phase === 'failed' && transfer.retryable && !!session && session.phase === 'active' &&
    session.session_id === transfer.session_id && session.generation === transfer.session_generation;
}
export const SESSION_LABELS: Record<TetherSession['phase'], string> = {
  starting: '正在启动', active: '正在接收相机文件', stopping: '正在停止', stopped: '已停止', error: '会话异常',
};
export const TRANSFER_LABELS: Record<TetherTransfer['phase'], string> = {
  queued: '等待传输', downloading: '正在下载', validating: '正在校验原片', importing: '正在导入', imported: '已导入',
  skipped: '已跳过', failed: '失败', outcome_unknown: '结果待查询', cancelled: '已取消',
};
