export const controls=['strength','shadows','midtones','highlights','size','roughness','colour'] as const;
export type Control=typeof controls[number];
export type Recipe={version:1;algorithm:'lrt-source-grain-v1';working_space:'extended-srgb-d65';size_unit:'source_pixels';seed:number}&Record<Control,number>;
export const labels:Record<Control,string>={strength:'颗粒效果',shadows:'阴影',midtones:'中间调',highlights:'高光',size:'颗粒大小（源像素）',roughness:'粗糙度',colour:'颗粒色彩'};
export function neutral():Recipe{return {version:1,algorithm:'lrt-source-grain-v1',working_space:'extended-srgb-d65',size_unit:'source_pixels',seed:1,strength:0,shadows:100,midtones:100,highlights:100,size:1.5,roughness:50,colour:0};}
export function checked(r:Recipe):Recipe {
 if(!r||Object.keys(r).sort().join()!==Object.keys(neutral()).sort().join()||r.version!==1||r.algorithm!=='lrt-source-grain-v1'||r.working_space!=='extended-srgb-d65'||r.size_unit!=='source_pixels'||!Number.isInteger(r.seed)||r.seed<0||r.seed>4294967295)throw Error('颗粒配方或随机种子无效');
 for(const key of controls){const lo=key==='size'?0.5:0,hi=key==='size'?16:100;if(typeof r[key]!=='number'||!Number.isFinite(r[key])||r[key]<lo||r[key]>hi)throw Error('颗粒数值超出范围');}return {...r};
}
export const requirements={parent:'LNX-REF-PC-32455-C-b82bd426d2',strength:'LNX-REF-PC-32455-C-3f4edf94f1',shadows:'LNX-REF-PC-32455-C-14eea5887b',midtones:'LNX-REF-PC-32455-C-76329825cf',highlights:'LNX-REF-PC-32455-C-fe5375e0a0',size:'LNX-REF-PC-32455-C-6f81c9689a',roughness:'LNX-REF-PC-32455-C-adf8922693',colour:'LNX-REF-PC-32455-C-8949a7f5ce'} as const;
