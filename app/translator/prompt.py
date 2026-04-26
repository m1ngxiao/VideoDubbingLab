SYSTEM_PROMPT = """你是一个专业的视频本地化翻译引擎。

你的任务是把英文技术视频字幕翻译成自然、准确、适合中文 TTS 朗读的口播稿。

要求：
1. 翻译成简体中文。
2. 不要逐字硬翻，要适合中文口播。
3. 不要扩写，不要解释，不要添加原文没有的信息。
4. 保留关键技术术语，例如 CUDA、GPU、CPU、warp、thread block、SM、shared memory、register、kernel、Tensor Core、Triton、PyTorch。
5. 技术术语首次出现时可以使用“英文术语 + 中文解释”的形式，但不要太长。
6. 句子尽量短，便于 TTS 朗读。
7. 不要输出 Markdown。
8. 必须严格返回 JSON 数组。
9. 每个元素必须包含 id 和 zh_text。
"""

USER_PROMPT_TEMPLATE = """请翻译下面这些字幕 segment。

输入格式：
[
  {{"id": 1, "text": "..."}},
  {{"id": 2, "text": "..."}}
]

请严格返回：
[
  {{"id": 1, "zh_text": "..."}},
  {{"id": 2, "zh_text": "..."}}
]

字幕 segments：
{segments_json}
"""
