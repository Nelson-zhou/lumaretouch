"""AUTHORED / UNRUN: frozen visual acknowledgment transport specifications."""
from pathlib import Path
import ast

ROOT=Path(__file__).parents[2]
ENGINE=ROOT/'engine/src/lumaretouch_engine'


def test_claim_checks_ack_before_consuming_frozen_plan():
    source=(ENGINE/'batch_preflight.py').read_text()
    claim=source.split('    def claim(',1)[1].split('    def finish(',1)[0]
    assert claim.index('acknowledgments(collarbone_review_ack,records)') < claim.index('self.finish(plan')
    assert "json.loads(target.people_json)['collarbone_visual']" in claim
    assert "if collarbone_required(plan):" in claim


def test_replay_requires_exact_original_coverage_ack():
    source=(ENGINE/'batch_preflight_controller.py').read_text()
    assert "canonical(p['collarbone_review_ack'])!=canonical(cached['collarbone_review_ack'])" in source
    assert "not collarbone_required(reviewed)" in source


def test_overflow_fallback_retains_coverage_and_png_hashes():
    source=(ENGINE/'batch_preflight.py').read_text()
    assert "ack['collarbone_review_ack']" in source
    assert "'coverage_sha256':r['coverage_sha256']" in source
    assert "'before_sha256':r['before']['sha256']" in source


def test_transport_sources_parse_without_importing_product():
    for name in ('batch_preflight.py','batch_preflight_controller.py','batch_sync.py'):
        ast.parse((ENGINE/name).read_text())


def test_native_binding_is_separate_from_main_and_retains_exact_ack():
    native=ROOT/'ui/src-tauri/src'
    assert 'pub(crate) mod collarbone;' in (native/'batch_api.rs').read_text()
    assert 'collarbone_review_ack:Option<Value>' in (native/'batch_api.rs').read_text()
    assert 'crate::batch_api::collarbone::binding(value)?' in (native/'receipt_host.rs').read_text()


def test_generic_batch_and_legacy_paths_refuse_collarbone_without_people_review():
    for name in ('batch_preflight_controller.py','batch_sync.py'):
        assert 'Collarbone batch requires confirmed or explicit target-owned people visual review' in (ENGINE/name).read_text()


def test_paged_image_transport_is_exact_and_never_a_mutation_retry():
    sync=(ENGINE/'batch_sync.py').read_text()
    assert 'retrieve(self.preflight,p)' in sync
    assert sync.index('if action == "collarbone_visual":') < sync.index('why = self.editor.guard')
    assert "any(key in p for key in ('document_id','revision','side','sha256'))" in sync
    source=(ENGINE/'batch_preflight_controller.py').read_text()
    assert 'prune(self.store)' in source
    assert 'prune(self)' in (ENGINE/'batch_preflight.py').read_text()
