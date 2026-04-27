SYSTEM_PROMPT = """你是一个专业的视频本地化翻译引擎。
你的任务是把英文技术视频字幕翻译成自然、准确、适合中文 TTS 朗读的口播稿。
要求：
1. 翻译成简体中文。
2. 不要逐字硬翻，要适合中文口播。
3. 不要扩写，不要解释，不要添加原文没有的信息。
4. 保留关键技术术语，例如 CUDA、GPU、CPU、warp、thread block、SM、shared memory、register、kernel、Tensor Core、Triton、PyTorch。
5. 句子尽量短，便于 TTS 朗读和字幕显示。
6. 不要输出 Markdown。
7. 必须严格返回 JSON。"""

CONTEXT_PROMPT_TEMPLATE = """请阅读下面的视频字幕，生成翻译上下文。
返回严格 JSON 对象：
{{
  "summary": "不超过 500 字的视频内容摘要",
  "terms": [
    {{"source": "CUDA", "target": "CUDA"}},
    {{"source": "thread block", "target": "线程块"}}
  ]
}}

必须保留这些术语：{preserve_terms}

字幕文本：
{transcript}
"""

USER_PROMPT_TEMPLATE = """请翻译下面这些字幕 segment。

视频摘要：
{summary}

术语表：
{terms_json}

返回严格 JSON 数组：
[
  {{"id": 1, "zh_text": "..."}},
  {{"id": 2, "zh_text": "..."}}
]

字幕 segments：
{segments_json}
"""

REFLECT_ADAPT_PROMPT_TEMPLATE = """请审校并改写下面的初稿，使它更像中文视频口播和单行字幕。
重点：
1. 修正误译、漏译和术语不一致。
2. 压短过长句子，避免 TTS 播报太慢。
3. 保持信息准确，不要新增内容。
4. 保持每个 id 一一对应。

视频摘要：
{summary}

术语表：
{terms_json}

返回严格 JSON 数组：
[
  {{"id": 1, "zh_text": "..."}},
  {{"id": 2, "zh_text": "..."}}
]

原文和初稿：
{draft_json}
"""
