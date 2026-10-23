/** Producer-bound metadata. u64 identities are decimal strings, never JS numbers. */
export interface CaptureDescriptor {
  version:1;epoch:string;shm_instance:string;capture_id:string;ticket:string;
  generation:string;seq:string;document_id:string;
  width:number;height:number;presentation_width:number;presentation_height:number;
  domain:'proxy-output'|'repair-input'|'source-input'|'wb-input'|'color-action-input';quality:'proxy-float-output'|'proxy-float-input'|'proxy-linear-input';profile:'working-srgb';
  picker_action?:'levels_black'|'levels_white'|'curve'|'hsl'|'colour_editor'|'id_background'|'id_background_reference'|'id_background_subject';
  picker_mode?:'original'|'reference'|'subject';source_binding?:Record<string,unknown>;
  picker_channel?:'master'|'red'|'green'|'blue'|'luminance'|null;source_stage?:string;
  /** Repair captures carry producer-owned source projection; the UI never derives source pixels from it. */
  projection?:Record<string,unknown>;
  recipe_document_id?:string;recipe_revision?:string;
  mask_overlay?:boolean;mask_suspended?:string|null;sample_valid_rows?:[number,number][]|null;
  /** null/omitted is the legacy mask slot; a retained group ID binds its own saved alpha. */
  mask_group_id?:string|null;
}
export interface CapturePoint {x:number;y:number;size:1|3|5|11}
export interface CaptureRegion {x:number;y:number;width:number;height:number}
export interface CaptureReadout {
  capture_id:string;ticket:string;request_id:string;request_ticket:string;
  success:boolean;error:string|null;descriptor?:CaptureDescriptor;region?:CaptureRegion;
  analysis?:{mean_srgb:[number,number,number]|null;mean_lab_d65:[number,number,number]|null;
    finite_samples:number;nonfinite_samples:number;samples:number};
}
