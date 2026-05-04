from app.audio.postprocess import LoudnessStats
from app.config import AppConfig
from app.qc import report as qc_report
from app.schemas import Segment, VideoTask


def test_qc_report_publishable_rules(tmp_path, monkeypatch):
    audio = tmp_path / "zh.wav"
    audio.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(qc_report, "measure_lufs", lambda path: LoudnessStats(integrated_lufs=-16.0, true_peak_db=-1.2))

    task = VideoTask(
        task_id="demo",
        work_dir=str(tmp_path),
        zh_audio_path=str(audio),
        segments=[
            Segment(
                id=1,
                start=0,
                end=1,
                duration=1,
                source_text="hello",
                target_text="你好",
                tts_audio_path=str(audio),
                tts_status="done",
                shift_ms=100,
            )
        ],
    )

    report = qc_report.build_qc_report(task, AppConfig())

    assert report["publishable"] is True
    assert report["publish_blockers"] == []
    assert report["max_shift_seconds"] == 0.1
