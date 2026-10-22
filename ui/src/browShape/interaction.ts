import {runBrowShapeRequest} from '../native';
import {createLatestIntent} from './latestIntent';
import {neutral,check,type BrowShape} from './model';
/** Module lifetime, not panel lifetime: collapsing a family never drops receipts. */
export const browInteraction=createLatestIntent<BrowShape>({
  check,equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  send:r=>runBrowShapeRequest({action:'edit',request_id:r.requestId,gesture_id:r.gestureId,
    document_id:r.documentId,face_id:r.faceId,control:r.control,recipe:r.recipe,base:r.base}),
  read:id=>runBrowShapeRequest({action:'status',request_id:id}),
},neutral());
