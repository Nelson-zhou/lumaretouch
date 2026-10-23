"""One neck inverse field under the shared BodyRef and common off-grid chain."""
from copy import deepcopy
import numpy as np
from . import neck_shape_state as S,neck_shape_native as N,body_pose_evidence as E,body_pose_operations as O,body_pose_manifest as M
class NeckField:
    operation_id=S.OPERATION_ID
    def __init__(self,row,support_asset,shape):
        self.record=E.check(row['record']);self.body_ref=self.record['body_ref'];self.shape=tuple(shape)
        self.input_binding_sha256=O.field_binding(row,self.operation_id);self.association=deepcopy(row['association']);self.associated_face_id=None
        self.recipe=S.check(row['operations'][self.operation_id]['recipe']);source=self.record['source'];E.whole_source_shape(source,self.shape)
        h,w=self.shape;sw,sh=source['width']-1,source['height']-1;self.render_scale=np.array([(w-1)/sw,(h-1)/sh]);self.render_scale.setflags(write=False)
        item=row['operations'][self.operation_id];review=item['review'];asset=O.check_support_record(support_asset)
        if review is None or review['operation_id']!=self.operation_id or review['body_ref']!=self.body_ref or review['points_sha256']!=self.record['points_sha256'] or review['visible_anchors']!=list(S.ANCHORS) or review['ownership_confirmed'] is not True or review['support_sha256']!=item['support_sha256']:raise ValueError('Neck-specific source review required')
        if E.content_digest(asset)!=item['support_sha256'] or asset['body_ref']!=self.body_ref or asset['operation_id']!=self.operation_id or asset['source']!=source or asset['points_sha256']!=self.record['points_sha256'] or asset['kind']!=S.SUPPORT_KIND:raise ValueError('Neck support ownership changed')
        if self.record['model_id']!=M.MODEL_ID or self.record['model_sha256']!=M.MODEL_SHA256:raise ValueError('Neck pose model identity changed; explicit reanalysis required')
        v=S.check_support(asset['data'],self.record);width=self.recipe['width'];negative='left' if v['anatomical_left']=='negative' else 'right';positive='right' if negative=='left' else 'left'
        self.state=np.array([v['center_x']*sw,v['upper']*sh,v['lower']*sh,*[n*(sw if i%2==0 else sh) for i,n in enumerate(v['head_box'])],*[n*(sw if i%2==0 else sh) for i,n in enumerate(v['transition_box'])],*[n*sw for n in v['negative']],*[n*sw for n in v['positive']],self.recipe['length'],width[negative],width[positive]],np.float64);self.state.setflags(write=False)
        self.max_displacement=float((abs(self.recipe['length'])*(self.state[2]-self.state[1])*.08+max(abs(width['left']),abs(width['right']))*.06*max(self.state[11:21]))*max(self.render_scale))
        box=np.array(v['transition_box']).reshape(2,2)*np.array([w-1,h-1]);self.bounds=(box[0],box[1]);center=box.mean(axis=0);center.setflags(write=False)
        self.supports=((center,float(np.linalg.norm(box[1]-box[0])*.5+self.max_displacement)),)
        # Admission invokes the same continuous native validation, not a fake ready flag.
        N.evaluate(self.state,np.array([[self.state[0],self.state[1]]]))
        self.facts={'operation_id':self.operation_id,'body_ref':deepcopy(self.body_ref),'status':'prepared-not-rendered','support_sha256':item['support_sha256'],'input_binding_sha256':self.input_binding_sha256,'runtime_quality_accepted':False,'background_and_garment_transition_may_move':True,'hidden_anatomy_inferred':False,'range_policy':'original-local-minus1-plus1','complete_head_hair_transport':True}
    def evaluate(self,p):return N.evaluate(self.state,np.asarray(p,np.float64)/self.render_scale)*self.render_scale
    def resident_bytes(self):return self.state.nbytes+self.render_scale.nbytes+sum(c.nbytes for c,_ in self.supports)
    def contains(self,p):
        p=np.asarray(p,np.float64);return np.all((p>self.bounds[0]-self.max_displacement)&(p<self.bounds[1]+self.max_displacement),axis=1)
    def envelope(self):return self.bounds[0]-self.max_displacement,self.bounds[1]+self.max_displacement
