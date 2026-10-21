"""Opening audit must survive polling, edits and save until another project opens."""
from PIL import Image
from test_protocol import engine, _create_and_save


def test_changed_source_notice_survives_state_and_save(engine, tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "red").save(path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="session", action="add", paths=[str(path)], thumbs=False)
    engine.wait_for("session_add")
    _, saved = _create_and_save(engine, tmp_path)
    Image.new("RGB", (64, 64), "blue").save(path)
    engine.send(cmd="project", action="open", path=saved["path"], doc="none")
    opened = engine.wait_for("project_opened", timeout=30)
    assert opened["auto_opened"] is None
    assert opened["changed_count"] == 1
    for action, event in [("state", "project_state"), ("save", "project_saved"),
                          ("state", "project_state")]:
        engine.send(cmd="project", action=action)
        notice = engine.wait_for(event, timeout=30)
        assert notice["changed_count"] == 1, notice
        assert notice["changed"][0]["path"] == str(path)
    engine.send(cmd="project", action="create", name="another", directory=str(tmp_path))
    created = engine.wait_for("project_created", timeout=30)
    assert not created.get("changed_count")
