from __future__ import annotations

import asyncio
import platform
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config import load_config
from app.pipeline.local_pipeline import run_local_pipeline
from app.pipeline.stages import build_tts_backend, get_llm_api_key
from app.pipeline.split_pipeline import run_dubbing_from_workdir, run_youtube_translation_pipeline
from app.pipeline.youtube_pipeline import run_youtube_pipeline
from app.utils.shell import command_exists

app = typer.Typer(help="VideoDubbingLab command line interface.")
console = Console()


@app.command("dub-youtube")
def dub_youtube(
    url: str = typer.Option(..., "--url", help="YouTube video URL."),
    output_dir: Path = typer.Option(Path("./data/output"), "--output-dir", help="Output directory."),
    config_path: Path = typer.Option(Path("./configs/default.yaml"), "--config", help="YAML config path."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from manifest when possible."),
    force: bool = typer.Option(False, "--force", help="Overwrite final output if it exists."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose runtime logging."),
) -> None:
    config = load_config(config_path)
    if verbose:
        config.runtime.log_level = "DEBUG"
    manifest = asyncio.run(run_youtube_pipeline(url, output_dir, config, resume=resume, force=force))
    console.print(f"[green]Done:[/green] {manifest.task.output_video_path}")


@app.command("translate-youtube")
def translate_youtube(
    url: str = typer.Option(..., "--url", help="YouTube video URL."),
    output_dir: Path = typer.Option(Path("./data/output"), "--output-dir", help="Output directory."),
    config_path: Path = typer.Option(Path("./configs/default.yaml"), "--config", help="YAML config path."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from manifest when possible."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose runtime logging."),
) -> None:
    config = load_config(config_path)
    if verbose:
        config.runtime.log_level = "DEBUG"
    manifest = asyncio.run(run_youtube_translation_pipeline(url, output_dir, config, resume=resume))
    console.print(f"[green]Translated:[/green] {manifest.task.work_dir}")
    console.print(f"[green]Preview subtitle:[/green] {manifest.task.zh_subtitle_path}")


@app.command("dub-workdir")
def dub_workdir(
    work_dir: Path = typer.Option(..., "--work-dir", exists=True, help="Translated task work directory."),
    config_path: Path = typer.Option(Path("./configs/cosyvoice3_rl.yaml"), "--config", help="YAML config path."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from manifest when possible."),
    force: bool = typer.Option(False, "--force", help="Overwrite final output if it exists."),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose runtime logging."),
) -> None:
    config = load_config(config_path)
    if verbose:
        config.runtime.log_level = "DEBUG"
    manifest = asyncio.run(run_dubbing_from_workdir(work_dir, config, resume=resume, force=force))
    console.print(f"[green]Done:[/green] {manifest.task.output_video_path}")


@app.command("batch-youtube")
def batch_youtube(
    url_file: Path = typer.Option(..., "--url-file", help="Text file containing one YouTube URL per line."),
    output_dir: Path = typer.Option(Path("./data/output"), "--output-dir", help="Output directory."),
    config_path: Path = typer.Option(Path("./configs/default.yaml"), "--config", help="YAML config path."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from manifest when possible."),
    force: bool = typer.Option(False, "--force", help="Overwrite final outputs if they exist."),
) -> None:
    config = load_config(config_path)
    urls = [line.strip() for line in url_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary: list[tuple[str, str, str]] = []
    for url in urls:
        try:
            manifest = asyncio.run(run_youtube_pipeline(url, output_dir, config, resume=resume, force=force))
            summary.append((url, "ok", manifest.task.output_video_path or ""))
        except Exception as exc:  # noqa: BLE001 - batch keeps going
            summary.append((url, "failed", str(exc)))
    table = Table(title="Batch Summary")
    table.add_column("URL")
    table.add_column("Status")
    table.add_column("Result")
    for row in summary:
        table.add_row(*row)
    console.print(table)


@app.command("dub-local")
def dub_local(
    video: Path = typer.Option(..., "--video", exists=True, help="Local source video."),
    subtitle: Path = typer.Option(..., "--subtitle", exists=True, help="Local SRT subtitle."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Single task output directory."),
    config_path: Path = typer.Option(Path("./configs/default.yaml"), "--config", help="YAML config path."),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from manifest when possible."),
    force: bool = typer.Option(False, "--force", help="Overwrite final output if it exists."),
) -> None:
    config = load_config(config_path)
    manifest = asyncio.run(run_local_pipeline(video, subtitle, output_dir, config, resume=resume, force=force))
    console.print(f"[green]Done:[/green] {manifest.task.output_video_path}")


@app.command("check-env")
def check_env(
    config_path: Path = typer.Option(Path("./configs/default.yaml"), "--config", help="YAML config path."),
) -> None:
    config = load_config(config_path)
    output_dir = Path(config.paths.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_file = output_dir / ".write_probe"
    writable = False
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        writable = True
    except OSError:
        writable = False

    table = Table(title="VideoDubbingLab Environment")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row("Python", "ok", platform.python_version())
    table.add_row("ffmpeg", "ok" if command_exists("ffmpeg") else "missing", "required for audio/video processing")
    table.add_row("ffprobe", "ok" if command_exists("ffprobe") else "missing", "required for media duration probing")
    table.add_row("yt-dlp", "ok" if command_exists("yt-dlp") else "missing", "required for YouTube download")
    table.add_row(config.llm.api_key_env, "ok" if get_llm_api_key(config) else "missing", "required for translation")
    table.add_row("output writable", "ok" if writable else "failed", str(output_dir))
    try:
        import torch  # type: ignore

        cuda_detail = f"torch {torch.__version__}, cuda={torch.cuda.is_available()}"
    except Exception:
        cuda_detail = "torch not installed; ok for baseline pipeline"
    table.add_row("CUDA", "info", cuda_detail)
    console.print(table)


@app.command("check-tts")
def check_tts(
    config_path: Path = typer.Option(Path("./configs/cosyvoice3_rl.yaml"), "--config", help="YAML config path."),
    text: str = typer.Option("你好，这是 Fun-CosyVoice3 RL 的中文配音测试。", "--text", help="Text to synthesize."),
    output: Path = typer.Option(Path("./data/output/tts_smoke_test.wav"), "--output", help="Output wav path."),
) -> None:
    config = load_config(config_path)
    backend = build_tts_backend(config)
    output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(
        backend.synthesize(
            text=text,
            out_path=output,
            speaker=config.tts.speaker,
            ref_audio=config.tts.ref_audio,
        )
    )
    console.print(f"[green]TTS ok:[/green] {output}")


if __name__ == "__main__":
    app()
