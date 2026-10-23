import type {SessionDoc} from '../native';
export interface LibraryQuery {
  rating: null | {op:'gte'|'lte'|'eq';value:number};
  flags:string[]; labels:string[]; edited:string[]; exported:string[];
  formats:string[]; orientations:string[]; trash:'active'|'trash'|'all'; search:string;
  sort:'capture_time'|'edit_time'|'rating'|'type'|'size'|'name'|'import'; direction:'asc'|'desc';
}
export interface LibraryResult {
  query:LibraryQuery; paths:string[]; session_id:string; source_ids:Record<string,string>;
  facts:Record<string,{edited:boolean|null;exported:boolean;[key:string]:unknown}>;
  request_id:string|null; error?:string|null;
}
export const defaultQuery=():LibraryQuery=>({rating:null,flags:[],labels:[],edited:[],exported:[],formats:[],orientations:[],trash:'active',search:'',sort:'import',direction:'asc'});
export function ratingOf(d:SessionDoc){const tag=d.tags.find(t=>/^rating:[0-5]$/.test(t));return tag?Number(tag.slice(7)):0;}
export function flagOf(d:SessionDoc){return d.tags.includes('flag:rejected')?'rejected':d.tags.includes('flag:accepted')?'accepted':'unflagged';}
export const FLAG_COLOR:Record<string,string>={'红':'#e06c6c','黄':'#e3c176','绿':'#7bbf8a','蓝':'#6f9fd8','紫':'#b48ad8'};
