import {runMouthShapeRequest} from '../native';
import {createLatestIntent} from '../browShape/latestIntent';
import {neutral,check,type MouthShape} from './model';
/** Same hardened one-inflight whole-intent protocol as brows, eyes and nose. */
export const mouthInteraction=createLatestIntent<MouthShape>({
  check,equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  send:r=>runMouthShapeRequest({action:'edit',request_id:r.requestId,gesture_id:r.gestureId,
    document_id:r.documentId,face_id:r.faceId,control:r.control,recipe:r.recipe,base:r.base}),
  read:id=>runMouthShapeRequest({action:'status',request_id:id}),
},neutral());
