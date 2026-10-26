# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable visible review; the existing document owner alone commits history."""
from copy import deepcopy
import uuid
import numpy as np
from . import hand_shape_state as S,hand_shape_runtime as R
from .optics_candidate_identity import fingerprint
from .hand_shape_review import display_image,overlay


def tag():return {'protocol':1,'family':S.FAMILY}


class Review:
    def __init__(self,engine):
        self.engine=engine;self.current=None;self.proposals={};self.previewed=None

    def invalidate(self):self.current=None;self.proposals={};self.previewed=None

    def capture(self):
        from .creative_derived_source import binding,analysis_rgb,record
        from .creative_derived_repairs import stack_digest
        from .local_mask_state import file_stamp,source_digest
        e=self.engine
        if record(e) is not None:raise ValueError('手部美型本版支持原始照片；不把旧原图支撑套到创意合成来源')
        row=e._docs[e._doc_index];version=e._document_versions().version(row);source=S.source(binding(e));state=e._capture_state()
        stamp=file_stamp(e._doc_path)
        if source_digest(e._doc_path)!=source['sha256'] or file_stamp(e._doc_path)!=stamp:raise ValueError('Hand original source changed after decode')
        fence=fingerprint({'load_id':e._load_id,'document_id':version.document_id,'workspace':e._document_versions().workspace,'revision':version.revision,'state':state,'source_stamp':stamp})
        if self.current is not None and self.current['fence']==fence:
            return {k:self.current[k] for k in ('source','repair_sha256','fence','pixels','recipe')}
        if state.get('_repair_ops'):
            # Existing repairs may have changed a contour. Review/model input
            # must be the genuine repaired pre-geometry source, not old _src_rgb.
            from . import portrait_fit_source as F
            from .neck_wrinkle_source_capture import capture as repaired_capture
            if source['width']*source['height']*80+128*1024*1024>R.budget():raise ValueError('Repaired hand source exceeds full-source review memory budget')
            active_row,active_token=F._active(e)
            repaired=repaired_capture(lambda **kw:F.capture(e,expected_source=source,**kw),tuple(state['_repair_ops']),source,byte_budget=R.budget(),cancelled=None)
            F._assert_active(e,active_row,active_token)
            values=np.frombuffer(repaired.content,np.float32).reshape(source['height'],source['width'],3)
            # Explicit model/display RGB8 encoding only; render source remains
            # original-bit-depth repaired pixels under the canonical export owner.
            pixels=np.empty(values.shape,np.uint8)
            for y in range(0,source['height'],32):
                stripe=values[y:y+32]
                if not np.isfinite(stripe).all() or np.any((stripe<0)|(stripe>1)):raise ValueError('Repaired hand proposal display does not support HDR/clipping')
                pixels[y:y+32]=np.rint(stripe*255).astype(np.uint8)
        else:pixels=np.asarray(analysis_rgb(e))
        if pixels.dtype!=np.uint8 or pixels.ndim!=3 or pixels.shape[2]!=3:raise ValueError('Hand source requires canonical RGB8 analysis pixels, not displayed/warped pixels')
        from .body_pose_evidence import whole_source_shape
        whole_source_shape({**source,'orientation':'exif_normalized_once'},pixels.shape[:2])
        if pixels.nbytes*2+32*1024*1024>R.budget():raise ValueError('Hand source preview exceeds memory admission')
        pixels=np.frombuffer(np.ascontiguousarray(pixels).tobytes(),np.uint8).reshape(pixels.shape)
        fence=fingerprint({'load_id':e._load_id,'document_id':version.document_id,'workspace':e._document_versions().workspace,'revision':version.revision,'state':state,'source_stamp':stamp})
        return {'source':source,'repair_sha256':stack_digest(state),'fence':fence,'pixels':pixels,'recipe':S.check(state.get('_hand_shape'))}

    def same(self):
        if self.current is None:raise ValueError('先重新获取当前原图的手部复核画面')
        capture=self.capture()
        if capture['fence']!=self.current['fence'] or capture['source']!=self.current['source']:
            self.invalidate();raise ValueError('照片、修复、历史或参数已改变；手部复核已失效')
        return capture

    def reference(self,payload):
        if payload!={}:raise ValueError('Reference does not accept supplied source pixels or landmarks')
        self.invalidate();value=self.capture();value['reference_id']=uuid.uuid4().hex;self.current=value
        from .hand_shape_native import capability
        from .hand_shape_model import status
        result={**tag(),'reference_id':value['reference_id'],'fence':value['fence'],'source':value['source'],
            'source_image':display_image(value['pixels']),'current_recipe':value['recipe'],'capability':capability(),'model':status()}
        self.same();return result

    def _reference(self,payload):
        if type(payload) is not dict or self.current is None or payload.get('reference_id')!=self.current['reference_id']:raise ValueError('Hand source reference expired')
        return self.same()

    def propose(self,payload):
        if set(payload)!={'reference_id'}:raise ValueError('Hand proposal accepts current source reference only')
        captured=self._reference(payload)
        from .hand_shape_model import analyse
        from .hand_shape_provenance import check_proposal
        result=analyse(captured['pixels'],captured['source'],byte_budget=R.budget())
        self.same();self.proposals={};self.previewed=None
        shared={k:deepcopy(result[k]) for k in ('version','source','model_id','model_sha256','backend_version','backend_code_sha256','input_rgb_sha256','input_dimensions')}
        for row in result['records']:
            proposal=check_proposal({**shared,**deepcopy(row)});self.proposals[proposal['proposal_id']]=proposal
        return {**tag(),'reference_id':self.current['reference_id'],'fence':captured['fence'],'proposals':deepcopy(result['records']),
            'census_complete':False,'visibility_verified':False,'limit_reached':result['limit_reached']}

    def _render(self,value):
        from .full_candidate_render import render
        e=self.engine;row=e._docs[e._doc_index];version=e._document_versions().version(row)
        state=e._capture_state();state['_hand_shape']=S.check(value)
        pixels,_=render(e,row,state,version.document_id,str(version.revision))
        return pixels

    def preview(self,payload):
        if set(payload)!={'reference_id','review','amounts'}:raise ValueError('Hand preview fields invalid')
        captured=self._reference(payload);review=S.validate_support(payload['review'],captured['source']);values=S.amounts(payload['amounts'])
        proposal=None
        if review['proposal_id'] is not None:
            proposal=self.proposals.get(review['proposal_id'])
            if proposal is None:raise ValueError('Model proposal is not a retained result from this exact current source review')
        recipe=S.check({'version':1,'source':captured['source'],'repair_sha256':captured['repair_sha256'],'review':review,'amounts':values,'proposal':deepcopy(proposal)})
        # Genuine complete-pipeline comparison; neither image is a hand-only crop.
        before=display_image(self._render(captured['recipe']));self.same()
        after=display_image(self._render(recipe));self.same()
        support=overlay(captured['pixels'],review,captured['source'])
        result={**tag(),'preview_id':uuid.uuid4().hex,'fence':captured['fence'],'before':before,'after':after,'overlay':support,'candidate_sha256':fingerprint(recipe),
            'facts':{'source':captured['source'],'strategy':'manual-visible-support' if proposal is None else 'model-proposal-manually-corrected-support',
            'one_hand_per_document':True,'one_source_geometry_sampler':True,'no_body_pose_required':True,'runtime_quality_accepted':False}}
        import json
        if len(json.dumps(result,separators=(',',':')).encode())>7*1024*1024:raise ValueError('Hand comparison exceeds transport budget; no oversized success receipt')
        self.previewed={'recipe':recipe,'result':deepcopy(result)};return result

    def confirm(self,payload):
        if type(payload) is not dict or set(payload)!={'preview_id','reviewed','before_sha256','after_sha256','overlay_sha256','candidate_sha256'} or payload['reviewed'] is not True or self.previewed is None:raise ValueError('Review the complete before/after and actual hand support overlay before confirmation')
        self.same();result=self.previewed['result']
        if payload['preview_id']!=result['preview_id'] or payload['candidate_sha256']!=result['candidate_sha256'] or any(payload[k+'_sha256']!=result[k]['sha256'] for k in ('before','after','overlay')):raise ValueError('Hand confirmation does not name the displayed exact candidate')
        return S.check(self.previewed['recipe'])
