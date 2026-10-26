/** Presentation-only readiness contract. The native owner remains authoritative. */
export interface ModelStatus {
  running:boolean;action?:string;error?:string;extension_id?:string;
  result?:{state?:string;phase?:string;installed?:boolean;ready?:boolean;readiness?:string;
    checkpoint_verified?:boolean;downloaded_bytes?:number;total_bytes?:number;resume_bytes?:number;error?:string};
}
export function extensionReady(status:ModelStatus|null):boolean {
  return !!status&&status.extension_id==='id-background-prompted-v1'&&!status.running&&!status.error&&status.result?.state==='installed'
    &&status.result.installed===true&&status.result.ready===true&&status.result.readiness==='cpu-probe-passed'
    &&status.result.checkpoint_verified===true&&!status.result.error;
}
export function extensionStatusLabel(status:ModelStatus|null):string {
  if(status?.running)return '处理中';
  if(extensionReady(status))return 'CPU 准备检查通过';
  switch(status?.result?.state){
    case 'installed':return '文件已安装 · 尚未准备好';
    case 'unsupported':return '基础运行环境不支持';
    case 'invalid':return '安装完整性异常';
    case 'error':return '准备失败';
    case 'cancelled':return '已取消，可重试';
    case 'not-installed':return '尚未安装';
    default:return '尚未核对';
  }
}
export function downloadProgress(status:ModelStatus|null):{done:number;total:number}|null {
  const done=status?.result?.downloaded_bytes,total=status?.result?.total_bytes;
  return typeof done==='number'&&typeof total==='number'&&Number.isSafeInteger(done)
    &&Number.isSafeInteger(total)&&done>=0&&total>0&&done<=total?{done,total}:null;
}
