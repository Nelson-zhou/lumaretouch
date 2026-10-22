import {runNoseShapeRequest} from '../native';
import {createLatestIntent} from '../browShape/latestIntent';
import {neutral,check,type NoseShape} from './model';
/** Module lifetime survives panel collapse; no duplicate edit after uncertainty. */
export const noseInteraction=createLatestIntent<NoseShape>({
  check,equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  send:r=>runNoseShapeRequest({action:'edit',request_id:r.requestId,gesture_id:r.gestureId,
    document_id:r.documentId,face_id:r.faceId,control:r.control,recipe:r.recipe,base:r.base}),
  read:id=>runNoseShapeRequest({action:'status',request_id:id}),
},neutral());
