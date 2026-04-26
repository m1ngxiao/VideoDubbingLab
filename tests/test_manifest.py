from app.pipeline.manifest import ManifestManager
from app.schemas import VideoTask


def test_manifest_roundtrip(tmp_path):
    task = VideoTask(task_id="demo", work_dir=str(tmp_path))
    manager = ManifestManager.load_or_create(tmp_path, task, resume=False)
    manager.mark_done("download")
    loaded = ManifestManager.load_or_create(tmp_path, task, resume=True)
    assert loaded.stage_done("download")
    assert loaded.manifest.task.task_id == "demo"
