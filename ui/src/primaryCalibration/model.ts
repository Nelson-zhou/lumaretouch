export type Primary='red'|'green'|'blue';
export type Control={hue:number;saturation:number};
export type Recipe={version:1;algorithm:'lrt-xy-primary-basis-v1';working_space:'linear-srgb-d65';red:Control;green:Control;blue:Control};
export const primaries:Primary[]=['red','green','blue'];
export function neutral():Recipe{return {version:1,algorithm:'lrt-xy-primary-basis-v1',working_space:'linear-srgb-d65',red:{hue:0,saturation:0},green:{hue:0,saturation:0},blue:{hue:0,saturation:0}};}
export function checked(r:Recipe):Recipe{
 if(!r||Object.keys(r).sort().join()!==Object.keys(neutral()).sort().join()||r.version!==1||r.algorithm!=='lrt-xy-primary-basis-v1'||r.working_space!=='linear-srgb-d65')throw Error('原色校准版本、工作空间或字段无效');
 const out=neutral();for(const k of primaries){const c=r[k];if(!c||Object.keys(c).sort().join()!=='hue,saturation')throw Error('原色校准字段无效');for(const f of ['hue','saturation'] as const){if(typeof c[f]!=='number'||!Number.isFinite(c[f])||Math.abs(c[f])>100)throw Error('原色校准数值需在 -100 至 100');out[k][f]=c[f];}}return out;
}
export const requirements={parent:'PC-32455-C-45230cc916',red:'PC-32455-C-e77705a980',green:'PC-32455-C-0c32421d72',blue:'PC-32455-C-d5582f85c3',red_hue:'PC-32455-C-e0d4cbbc08',red_saturation:'PC-32455-C-22cf1cc100',green_hue:'PC-32455-C-32971f959b',green_saturation:'PC-32455-C-667f8eaedd',blue_hue:'PC-32455-C-a4fd10da21',blue_saturation:'PC-32455-C-e087104fdd'} as const;
