# VideoDubbingLab

VideoDubbingLab 是一个面向批量生产的 YouTube 英文视频转中文配音流水线。输入 YouTube URL，输出中文配音视频、中文字幕、对齐音频、断点续跑 manifest 和 QC 报告。

默认链路：

```text
YouTube URL
-> yt-dlp 单次下载视频 / 音频 / 字幕 / metadata
-> 英文手工字幕优先，英文自动字幕兜底，无字幕时可选 ASR
-> duration-aware LLM 翻译 + translation cache
-> batch/queue TTS + TTS cache + 音频后处理
-> 有界时间线对齐
-> 原音 ducking + ffmpeg mux
-> qc_report.json
```

## 最终输出

每个视频会生成一个独立 workdir，核心文件是：

```text
final_zh_dubbed.mp4
zh.srt
zh_audio_aligned.wav
manifest.json
qc_report.json
preview_60s.mp4        # 可选，mux.create_preview=true 时生成
```

中间产物包括 `source.mp4`、`source.audio.wav`、`source.en.srt` 或 `source.en.asr.srt`、`zh_tts_segments/`、`download_manifest.json` 和 `logs/run.log`。这些文件都用于定位问题和断点续跑。

## 云服务器快速开始

下面是一条从 `git clone` 到跑出中文配音视频的完整流程，适合 Ubuntu + NVIDIA 3090 云服务器。

### 1. 登录服务器并安装系统依赖

```bash
ssh root@YOUR_SERVER_IP

apt update
apt install -y git git-lfs ffmpeg sox tmux curl python3 python3-venv python3-pip
git lfs install

ffmpeg -version
python3 --version
```

### 2. 克隆仓库

HTTPS 方式：

```bash
cd /opt
git clone https://github.com/m1ngxiao/VideoDubbingLab.git
cd /opt/VideoDubbingLab
```

SSH 方式：

```bash
cd /opt
git clone git@github.com:m1ngxiao/VideoDubbingLab.git
cd /opt/VideoDubbingLab
```

如果你要使用 Codex 推上去的开发分支：

```bash
git fetch origin
git checkout codex/videolingo-parity-pipeline
```

### 3. 安装主项目 Python 环境

```bash
cd /opt/VideoDubbingLab
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -U yt-dlp
```

配置 LLM key：

```bash
export DEEPSEEK_API_KEY="your_deepseek_key"
```

建议写入 shell 配置，避免重连后丢失：

```bash
echo 'export DEEPSEEK_API_KEY="your_deepseek_key"' >> ~/.bashrc
source ~/.bashrc
```

### 4. 安装 CosyVoice3 RL TTS 服务

TTS 大模型建议作为常驻 GPU 服务运行，主 pipeline 只做下载、翻译、缓存、编排、对齐和合成。

推荐目录：

```text
/opt/VideoDubbingLab
/opt/tts/CosyVoice
/data/models/tts/Fun-CosyVoice3-0.5B-2512
```

一键安装：

```bash
cd /opt/VideoDubbingLab
bash scripts/setup_cosyvoice3_rl_ubuntu.sh
```

启动 TTS 服务，建议放在 tmux 里：

```bash
tmux new -s cosyvoice

cd /opt/VideoDubbingLab
conda activate cosyvoice

export COSYVOICE_ROOT=/opt/tts/CosyVoice
export COSYVOICE_MODEL_DIR=/data/models/tts/Fun-CosyVoice3-0.5B-2512
export COSYVOICE_USE_RL=1
export COSYVOICE_PROMPT_TEXT="You are a helpful assistant.<|endofprompt|>希望你以后能够做得比我还好。"

bash scripts/run_cosyvoice3_rl_server.sh
```

按 `Ctrl-b` 然后按 `d` 可以退出 tmux 但保持 TTS 服务运行。重新进入：

```bash
tmux attach -t cosyvoice
```

健康检查：

```bash
curl http://127.0.0.1:9880/health
```

测试 TTS：

```bash
cd /opt/VideoDubbingLab
source .venv/bin/activate

python -m app.cli check-tts \
  --config ./configs/cosyvoice3_rl.yaml \
  --text "你好，这是一段中文配音测试。" \
  --output ./data/output/tts_smoke_test.wav
```

### 5. 跑一个 YouTube 视频

新开一个终端或 tmux session，保持 TTS 服务继续运行。

```bash
cd /opt/VideoDubbingLab
source .venv/bin/activate
export DEEPSEEK_API_KEY="your_deepseek_key"

python -m app.cli check-env --config ./configs/cosyvoice3_rl.yaml

python -m app.cli dub-youtube \
  --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" \
  --output-dir ./data/output \
  --config ./configs/cosyvoice3_rl.yaml \
  --resume
```

完成后查看输出：

```bash
find ./data/output -maxdepth 3 -name "final_zh_dubbed.mp4" -print
find ./data/output -maxdepth 3 -name "qc_report.json" -print
```

检查 QC：

```bash
cat ./data/output/*/qc_report.json
```

如果 `publishable` 是 `true`，核心成片在：

```text
./data/output/{video_id}_{safe_title}/final_zh_dubbed.mp4
```

### 6. 批量跑 YouTube URL

准备 URL 文件：

```bash
mkdir -p data
nano data/urls.txt
```

每行一个 URL：

```text
https://www.youtube.com/watch?v=aaa
https://www.youtube.com/watch?v=bbb
```

运行：

```bash
python -m app.cli batch-youtube \
  --url-file ./data/urls.txt \
  --output-dir ./data/output \
  --config ./configs/cosyvoice3_rl.yaml \
  --jobs 2 \
  --resume
```

批量任务会输出：

```text
data/output/batch_summary.json
```

单 3090 推荐保持 TTS 单并发：

```yaml
tts_batch:
  concurrency: 1
  max_batch_size: 8

batch:
  jobs: 2
  download_concurrency: 2
  translate_concurrency: 2
  tts_concurrency: 1
  mux_concurrency: 1
```

### 7. 断点续跑和只跑某些阶段

默认开启 `--resume`。中断后重新执行同一条命令即可复用已完成产物。

只跑翻译：

```bash
python -m app.cli dub-youtube \
  --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" \
  --output-dir ./data/output \
  --config ./configs/cosyvoice3_rl.yaml \
  --from-stage download \
  --to-stage translate \
  --resume
```

从已翻译 workdir 继续配音和 mux：

```bash
python -m app.cli dub-workdir \
  --work-dir ./data/output/YOUR_TASK_DIR \
  --config ./configs/cosyvoice3_rl.yaml \
  --from-stage tts \
  --to-stage qc_report \
  --resume
```

## ASR fallback

默认不启用 ASR，避免普通 CI 或轻量机器强依赖大模型。无字幕视频需要手动开启：

```yaml
asr:
  enabled: true
  backend: "faster_whisper"
  model_size: "small"
  device: "cuda"
  language: "en"
```

并在服务器安装对应依赖，例如：

```bash
source .venv/bin/activate
python -m pip install faster-whisper
```

也可以改用 `whisperx`，但需要自行准备它的运行依赖。

## 推送代码到你的 GitHub 仓库

不要把 `data/output/*.mp4` 这类大视频直接提交到 Git。生成的视频建议用服务器下载、对象存储、网盘、GitHub Release 或 Git LFS 管理。

确认 `.gitignore` 没有把输出文件纳入提交：

```bash
git status --short
```

提交代码改动：

```bash
git checkout -b codex/production-dubbing-pipeline
git add README.md app configs tests tts_servers
git commit -m "Build production YouTube dubbing pipeline"
```

推送到 GitHub：

```bash
git push -u origin codex/production-dubbing-pipeline
```

然后到 GitHub 页面打开 Pull Request。

如果你确实要把最终视频也传到 GitHub，推荐使用 GitHub Release：

```bash
gh auth login
gh release create dubbed-demo-v1 \
  ./data/output/YOUR_TASK_DIR/final_zh_dubbed.mp4 \
  ./data/output/YOUR_TASK_DIR/zh.srt \
  ./data/output/YOUR_TASK_DIR/qc_report.json \
  --title "Dubbed demo v1" \
  --notes "Chinese dubbed output generated by VideoDubbingLab."
```

## 常用命令

环境检查：

```bash
python -m app.cli check-env --config ./configs/cosyvoice3_rl.yaml
```

TTS 检查：

```bash
python -m app.cli check-tts --config ./configs/cosyvoice3_rl.yaml
```

单视频：

```bash
python -m app.cli dub-youtube --url "https://www.youtube.com/watch?v=xxxx" --config ./configs/cosyvoice3_rl.yaml
```

只翻译：

```bash
python -m app.cli translate-youtube --url "https://www.youtube.com/watch?v=xxxx" --config ./configs/cosyvoice3_rl.yaml
```

本地视频 + SRT/VTT：

```bash
python -m app.cli dub-local \
  --video ./data/input/demo.mp4 \
  --subtitle ./data/input/demo.en.srt \
  --output-dir ./data/output/demo \
  --config ./configs/cosyvoice3_rl.yaml
```

## QC 报告

`qc_report.json` 至少包含：

- `total_segments`
- `missing_tts_segments`
- `failed_tts_segments`
- `overflow_segments`
- `max_shift_seconds`
- `avg_shift_seconds`
- `total_duration_source`
- `total_duration_output`
- `duration_diff_seconds`
- `loudness_lufs`
- `true_peak_db`
- `warnings`
- `publishable`
- `publish_blockers`

默认 publishable 判定：

- 没有缺失 TTS
- 没有失败 TTS
- 最大 shift 不超过 `qc.max_shift_seconds`
- 输出时长差不超过 `qc.max_duration_diff_seconds`
- true peak 不高于 -1 dB
- overflow 比例不超过 `qc.max_overflow_ratio`

## 测试

```bash
pytest
```
