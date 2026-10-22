from types import SimpleNamespace
import pytest
from lumaretouch_engine.color_action_readiness import require_warm_prefix


def fixture():
    # The default normalized filter key, including the repaired source version.
    pipe=SimpleNamespace(repair_version=7,retouched=object(),filter_key=(12,.0006,4,0.,0.,1.,7),
        light_version=2,light_exposure=.5,light_radius=6,light_src=object(),light_res=object(),
        deform_version=3,deform_amounts={'face':.2},high_precision_warp=False,_deform_warp=None)
    pipe._filter_parameters=lambda r,e,g,mg,bg,rf:(int(r),float(e),int(rf),float(g),float(mg),float(bg))
    pipe.has_light=lambda:True;pipe.has_deform=lambda:True
    pipe.light_src_key=(7,2,.5,6);pipe.light_res_key=(pipe.filter_key,2,.5,6)
    pipe._deform_warp_key=(3,(('face',.2),),False)
    return pipe


def test_warm_identity_deformation_none_is_valid_and_zero_strength_needs_no_filter_result():
    pipe=fixture();require_warm_prefix(pipe,.5,{})
    pipe.retouched=None;pipe.filter_key=None;pipe.light_res=None;pipe.light_res_key=None
    require_warm_prefix(pipe,0,{})
    pipe.light_src=None
    with pytest.raises(ValueError,match='source light cache'):require_warm_prefix(pipe,0,{})


@pytest.mark.parametrize('field,value',[
    ('repair_version',8),('filter_key',None),('retouched',None),
    ('light_version',3),('light_exposure',.6),('light_radius',7),('light_res',None),
    ('deform_version',4),('deform_amounts',{'face':.3}),('high_precision_warp',True),
])
def test_any_stale_cache_owner_or_parameter_requires_completed_normal_preview(field,value):
    pipe=fixture();setattr(pipe,field,value)
    with pytest.raises(ValueError):require_warm_prefix(pipe,.5,{})


@pytest.mark.parametrize('params',[{'radius':13},{'eps':.001},{'texture_radius':5},{'detail_gain':2},{'mid_gain':.5},{'broad_gain':.5}])
def test_filter_key_uses_the_actual_complete_normalized_recipe(params):
    with pytest.raises(ValueError,match='filter cache'):require_warm_prefix(fixture(),.5,params)
