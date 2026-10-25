// SPDX-License-Identifier: GPL-3.0-or-later
import type {ComponentProps} from 'react';
import {chooseImportFolder} from '../native';
import {LibraryGallery} from './Gallery';

/** Existing folder import and gallery, extracted intact from the capped App. */
export function LibraryWorkspace({busy, exporting, setBusy, importFolder, refresh, onError, ...gallery}: ComponentProps<typeof LibraryGallery> & {
  busy: boolean; exporting: boolean; setBusy: (value: boolean) => void;
  importFolder: (folder: string) => Promise<unknown>; refresh: () => Promise<unknown>; onError: (message: string) => void;
}) {
  async function addFolder() {
    setBusy(true);
    try {
      const folder = await chooseImportFolder();
      if (folder) {await importFolder(folder); await refresh();}
    } catch (error) {onError(String(error));} finally {setBusy(false);}
  }
  return <>
    <button type="button" disabled={busy || exporting} onClick={() => void addFolder()}>添加文件夹（保留导入层级，可继续添加多个目录）</button>
    <LibraryGallery {...gallery}/>
  </>;
}
