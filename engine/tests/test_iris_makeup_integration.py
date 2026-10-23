# UNRUN source-route fixtures, not real-photo acceptance.
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def text(path):return (ROOT/path).read_text()
def test_canonical_pipeline_routes():
    for path,token in [('engine/src/lumaretouch_engine/people_algorithms.py','IRIS.OP'),('engine/src/lumaretouch_engine/people_owned_inputs.py',"'iris_makeup_assets': engine._people_support"),('engine/src/lumaretouch_engine/people_engine_runtime.py',"iris_makeup_assets=snapshot.get('support_assets',{})"),('engine/src/lumaretouch_engine/people_project.py','validate_iris_support(value)'),('engine/src/lumaretouch_engine/people_scope.py',"fields[IRIS]='_iris_makeup_preset'"),('ui/src/App.tsx','irisMakeupPanel={<IrisMakeupPanel'),('ui/src-tauri/src/people_api.rs','"iris_review"')]:assert token in text(path)
def test_order_and_independent_review():
    s=text('engine/src/lumaretouch_engine/vram.py')
    stages=['blush_makeup','lipstick','eyeliner','eyelash','brow_makeup','iris_makeup','hair_colour','eye_light']
    indices=[s.index("source_effect(self,'"+stage+"',out)") for stage in stages]
    assert indices==sorted(indices)
    s=text('engine/src/lumaretouch_engine/iris_makeup_reference.py')
    assert 'min(radii)*scale<8' in s
    assert 'body_pose_commands import source_preview' not in text('engine/src/lumaretouch_engine/iris_makeup_host.py')
