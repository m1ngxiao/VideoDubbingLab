from app.config import AppConfig
from app.pipeline import split_pipeline
from app.pipeline.manifest import ManifestManager
from app.schemas import Segment, VideoTask


async def test_dub_workdir_rebases_manifest_paths_and_continues(tmp_path, monkeypatch):
    (tmp_path / "source.mp4").write_text("video", encoding="utf-8")
    task = VideoTask(
        task_id="demo",
        work_dir="C:/old/output/demo",
        source_video_path="C:/old/output/demo/source.mp4",
        segments=[
            Segment(id=1, start=0, end=1, duration=1, source_text="Hello", target_text="你好"),
        ],
    )
    manager = ManifestManager.load_or_create(tmp_path, task, resume=False)
    for stage in ["download", "parse_subtitle", "reflow_subtitle", "translate", "plan_dubbing"]:
        manager.mark_done(stage)

    async def fake_tts_stage(task, manager, config):
        task.segments[0].tts_audio_path = str(tmp_path / "zh_tts_segments" / "000001.wav")
        return task

    def fake_align_audio_stage(task, manager, config):
        task.zh_audio_path = str(tmp_path / "zh_audio_aligned.wav")
        return task

    def fake_write_subtitle_stage(task):
        task.zh_subtitle_path = str(tmp_path / "zh.srt")
        return task

    def fake_mux_stage(task, config, force=False):
        task.output_video_path = str(tmp_path / "final_zh_dubbed.mp4")
        return task

    monkeypatch.setattr(split_pipeline, "tts_stage", fake_tts_stage)
    monkeypatch.setattr(split_pipeline, "align_audio_stage", fake_align_audio_stage)
    monkeypatch.setattr(split_pipeline, "write_subtitle_stage", fake_write_subtitle_stage)
    monkeypatch.setattr(split_pipeline, "mux_stage", fake_mux_stage)

    manifest = await split_pipeline.run_dubbing_from_workdir(tmp_path, AppConfig(), resume=True)

    assert manifest.task.source_video_path == str((tmp_path / "source.mp4").resolve())
    assert manifest.stage_done("tts")
    assert manifest.stage_done("align_audio")
    assert manifest.stage_done("write_subtitle")
    assert manifest.stage_done("mux")
    assert manifest.task.output_video_path.endswith("final_zh_dubbed.mp4")
