import {runEyeShapeRequest} from '../native';
import {createLatestIntent} from '../browShape/latestIntent';
import {neutral,check,type EyeShape} from './model';
/** Module lifetime survives panel collapse; no duplicate edit after uncertainty. */
export const eyeInteraction=createLatestIntent<EyeShape>({
  check,equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  send:r=>runEyeShapeRequest({action:'edit',request_id:r.requestId,gesture_id:r.gestureId,
    document_id:r.documentId,face_id:r.faceId,control:r.control,recipe:r.recipe,base:r.base,...(r.peopleContext?{people_context:r.peopleContext}:{})}),
  read:id=>runEyeShapeRequest({action:'status',request_id:id}),
},neutral());
