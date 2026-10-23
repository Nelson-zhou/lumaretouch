"""UNRUN integration fixtures; requires authorized local product imports/build."""
import unittest
from lumaretouch_engine import scope as SC, colour_grading_state as S
from lumaretouch_engine.colour_grading_adapters import validate_records
from lumaretouch_engine import project

class IntegratedGrading(unittest.TestCase):
    def test_scope_roundtrip_preserves_unrelated_state(self):
        recipe=S.neutral();recipe['global']['saturation']=45
        original={'_unrelated':{'keep':1},S.KEY:S.neutral()}
        result=SC.apply_modules(original,{'lnx.colour_grading.v1':{'recipe':recipe}})
        self.assertEqual(result['_unrelated'],original['_unrelated'])
        self.assertEqual(S.from_state(result),recipe)
        self.assertEqual(S.from_state(original),S.neutral())
    def test_v17_and_previous_schema_constants(self):
        self.assertEqual(project.SCHEMA,'lrt.project.v17')
        self.assertEqual(project.TONE_SCHEMA,'lrt.project.v16')
        self.assertEqual(project.CUBE_SCHEMA,'lrt.project.v15')
        self.assertEqual(project.HAIR_SCHEMA,'lrt.project.v14')
    def test_no_hidden_grade_in_legacy_nested_history(self):
        value={'history':[{S.KEY:S.neutral()}]}
        with self.assertRaises(ValueError):validate_records(value,allowed=False)
        validate_records(value,allowed=True)
