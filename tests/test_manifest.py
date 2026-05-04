from app.pipeline.manifest import ManifestManager
from app.pipeline.stages import STAGES
from app.schemas import VideoTask


def test_manifest_roundtrip(tmp_path):
    task = VideoTask(task_id="demo", work_dir=str(tmp_path))
    manager = ManifestManager.load_or_create(tmp_path, task, resume=False)
    manager.mark_done("download")
    loaded = ManifestManager.load_or_create(tmp_path, task, resume=True)
    assert loaded.stage_done("download")
    assert loaded.manifest.task.task_id == "demo"


def test_stage_list_matches_actual_pipeline_without_extract_audio():
    assert "extract_audio" not in STAGES
    assert STAGES[:3] == ["download", "parse_subtitle", "reflow_subtitle"]
    assert STAGES[-1] == "qc_report"
