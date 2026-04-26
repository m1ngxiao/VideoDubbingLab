from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def write_silence_wav(path: str | Path, duration: float, sample_rate: int = 24000) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    samples = max(0, int(round(duration * sample_rate)))
    data = np.zeros(samples, dtype=np.float32)
    sf.write(str(output_path), data, sample_rate)
    return output_path
