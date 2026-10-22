/** Extracted existing App navigation; sample management is reachable before opening a photo. */
export type Workspace = 'projects' | 'library' | 'retouch' | 'creative' | 'export';
export function WorkspaceTopbar({ workspace, onWorkspace, busy, hasImage, currentPath, onOpenPhoto, libraryEnabled, onLibrary }: {
  workspace: Workspace; onWorkspace: (value: Workspace) => void; busy: boolean; hasImage: boolean;
  currentPath?: string | null; onOpenPhoto: () => void; libraryEnabled: boolean; onLibrary: () => void;
}) {
  return <header className="topbar">
    <span className="brand">LumaRetouch</span>
    <button className="tb openPhoto" onClick={onOpenPhoto} disabled={busy}>打开照片</button>
    <nav className="wsTabs" aria-label="工作区">
      {([['projects', '项目管理'], ['library', '图库'], ['retouch', '精修'], ['creative', '创意'], ['export', '批量导出']] as const)
        .map(([value, label]) => <button key={value} className={workspace === value ? 'on' : ''} onClick={() => onWorkspace(value)}>{label}</button>)}
    </nav>
    <button className="tb" onClick={onLibrary} disabled={!libraryEnabled}
      title={libraryEnabled ? '管理自己导入或保存的本地样片' : '请先启动支持本地样片库的配套引擎'}>样片库</button>
    <span className="topHint">{hasImage ? (currentPath?.split('/').pop() ?? '当前照片') : '本地 · 离线'}</span>
    <button className="tb primary exportBtn" onClick={() => onWorkspace('export')} disabled={!hasImage}>导出照片</button>
  </header>;
}
