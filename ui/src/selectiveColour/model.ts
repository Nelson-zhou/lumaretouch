export const ranges=['reds','yellows','greens','cyans','blues','magentas','whites','neutrals','blacks'] as const;
export const inks=['cyan','magenta','yellow','black'] as const;
export type Range=typeof ranges[number];
export type Ink=typeof inks[number];
export type Recipe={version:1;algorithm:'lrt-rgb-ink-v1';working_space:'extended-srgb-d65';method:'relative'|'absolute';ranges:Record<Range,Record<Ink,number>>};
export function neutral():Recipe{return {version:1,algorithm:'lrt-rgb-ink-v1',working_space:'extended-srgb-d65',method:'relative',ranges:Object.fromEntries(ranges.map(k=>[k,{cyan:0,magenta:0,yellow:0,black:0}])) as Recipe['ranges']};}
export function checked(r:Recipe):Recipe{
 if(!r||Object.keys(r).sort().join()!==Object.keys(neutral()).sort().join()||r.version!==1||r.algorithm!=='lrt-rgb-ink-v1'||r.working_space!=='extended-srgb-d65'||!['relative','absolute'].includes(r.method))throw Error('可选颜色版本、模式或字段无效');
 if(!r.ranges||Object.keys(r.ranges).sort().join()!==[...ranges].sort().join())throw Error('可选颜色需要全部九个色域');
 const out=neutral();out.method=r.method;
 for(const k of ranges){const row=r.ranges[k];if(!row||Object.keys(row).sort().join()!==[...inks].sort().join())throw Error('每个色域需要全部四个 CMYK 数值');
 for(const ink of inks){const v=row[ink];if(typeof v!=='number'||!Number.isFinite(v)||v< -100||v>100)throw Error('CMYK 数值必须介于 -100 与 100');out.ranges[k][ink]=v;}}
 return out;
}
export const requirements={parent:'LNX-REF-PC-32455-C-63924bf039',reds:'LNX-REF-PC-32455-C-ad5041d8a3',yellows:'LNX-REF-PC-32455-C-b2931a80c2',greens:'LNX-REF-PC-32455-C-c762b47e72',cyans:'LNX-REF-PC-32455-C-f7a02ddd85',blues:'LNX-REF-PC-32455-C-5a61ebc24d',magentas:'LNX-REF-PC-32455-C-961b8a72e5',whites:'LNX-REF-PC-32455-C-baf4810187',neutrals:'LNX-REF-PC-32455-C-322f0a8b89',blacks:'LNX-REF-PC-32455-C-1b6b0ac442',cyan:'LNX-REF-PC-32455-C-1162cf5707',magenta:'LNX-REF-PC-32455-C-aef234aebb',yellow:'LNX-REF-PC-32455-C-d25cf174ad',black:'LNX-REF-PC-32455-C-0e8f77b2e7',relative:'LNX-REF-PC-32455-C-94a9cc59c6',absolute:'LNX-REF-PC-32455-C-e7ab820b5d'} as const;
