/** Producer-bound metadata. u64 identities are decimal strings, never JS numbers. */
export interface CaptureDescriptor {
  version:1;epoch:string;shm_instance:string;capture_id:string;ticket:string;
  generation:string;seq:string;document_id:string;
  width:number;height:number;presentation_width:number;presentation_height:number;
  domain:'proxy-output'|'repair-input';quality:'proxy-float-output'|'proxy-float-input';profile:'working-srgb';
  /** Repair captures carry producer-owned source projection; the UI never derives source pixels from it. */
  projection?:Record<string,unknown>;
  recipe_document_id?:string;recipe_revision?:string;
}
export interface CapturePoint {x:number;y:number;size:1|3|5|11}
export interface CaptureRegion {x:number;y:number;width:number;height:number}
export interface CaptureReadout {
  capture_id:string;ticket:string;request_id:string;request_ticket:string;
  success:boolean;error:string|null;descriptor?:CaptureDescriptor;region?:CaptureRegion;
  analysis?:{mean_srgb:[number,number,number]|null;mean_lab_d65:[number,number,number]|null;
    finite_samples:number;nonfinite_samples:number;samples:number};
}
