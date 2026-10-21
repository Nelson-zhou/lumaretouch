"""Architecture ratchets: enforce dependency direction, not arbitrary file splitting."""
from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'

def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ''
            yield from (alias.name for alias in node.names)

def test_extracted_policy_and_controller_do_not_import_engine_or_heavy_runtime():
    for name in ('history_policy.py', 'inspection_controller.py', 'batch_sync.py', 'history_controller.py', 'levels_controller.py'):
        source=(ENGINE/name).read_text(encoding='utf-8')
        names=set(imports(ENGINE/name))
        assert not {'server','Engine','torch','vram','project','session'} & names
        assert 'self._engine' not in source and 'self.engine' not in source
    assert set(imports(ENGINE/'history_policy.py')) <= {'json','hashlib'}

def test_diagnostics_depend_on_ports_not_on_app_component():
    for path in list((ROOT/'ui/src/diagnostics').glob('*.ts')) + list((ROOT/'ui/src/projects').glob('*.ts*')):
        source=path.read_text(encoding='utf-8')
        assert not re.search(r'''from\s*['"][^'"]*/App(?:\.tsx?)?['"]''',source)
        assert 'import.meta.env.DEV' not in source

def test_coordination_files_have_no_new_growth_without_explicit_boundary_review():
    # These caps freeze this extraction's baseline. They are NOT a quality score.
    # New responsibilities belong in modules; deliberate wiring growth requires
    # a reviewed boundary update, not silently increasing the threshold.
    for name, cap in [('ui/src/App.tsx',2150),('ui/src-tauri/src/main.rs',2030),
                      ('engine/src/lumaretouch_engine/server.py',7010)]:
        assert len((ROOT/name).read_text(encoding='utf-8').splitlines()) <= cap, name
