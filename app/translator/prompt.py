SYSTEM_PROMPT = """你是一个专业的视频本地化翻译引擎。
你的任务是把英文技术视频字幕翻译成自然、准确、适合中文 TTS 朗读的简体中文口播稿。
要求：
1. 不要逐字硬翻，要符合中文口播表达。
2. 不要解释，不要输出 Markdown，不要添加原文没有的信息。
3. 保留关键技术术语，例如 CUDA、GPU、CPU、warp、thread block、SM、shared memory、register、kernel、Tensor Core、Triton、PyTorch。
4. 每段必须考虑可用时长和 max_zh_chars，优先短句、清楚、可朗读。
5. 必须严格返回 JSON。"""

CONTEXT_PROMPT_TEMPLATE = """请阅读下面的视频字幕，生成全片翻译上下文。
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

USER_PROMPT_TEMPLATE = """请翻译下面这些字幕 segments。

视频摘要：
{summary}

术语表：
{terms_json}

每个 segment 都包含：
- id
- text: 英文原文
- duration: 该段可用秒数
- max_zh_chars: 推荐中文最大字数

返回严格 JSON 数组，数组项字段必须为：
[
  {{
    "id": 1,
    "zh_text": "自然准确的中文口播译文",
    "short_zh_text": "更短但信息仍准确的译文",
    "estimated_seconds": 1.2,
    "notes": "可为空字符串"
  }}
]

estimated_seconds 是你估计 zh_text 的中文 TTS 朗读秒数。如果 zh_text 可能超时，请给出明显更短的 short_zh_text。

字幕 segments：
{segments_json}
"""

REFLECT_ADAPT_PROMPT_TEMPLATE = """请审校并改写下面的中文初稿，使它更像中文技术视频口播，并满足时长约束。
重点：
1. 修正误译、漏译和术语不一致。
2. 压短过长句子，优先适配 duration 和 max_zh_chars。
3. 保持信息准确，不要新增内容。
4. 保持每个 id 一一对应。

视频摘要：
{summary}

术语表：
{terms_json}

返回严格 JSON 数组，数组项字段必须为：
[
  {{
    "id": 1,
    "zh_text": "自然准确的中文口播译文",
    "short_zh_text": "更短但信息仍准确的译文",
    "estimated_seconds": 1.2,
    "notes": "可为空字符串"
  }}
]

原文和初稿：
{draft_json}
"""

COMPRESS_PROMPT_TEMPLATE = """请把下面的中文译文压缩到更适合 TTS 朗读的版本。
要求：
1. 保留核心信息和术语。
2. 不要新增信息。
3. 目标时长：{duration:.2f} 秒以内。
4. 推荐最大中文字数：{max_zh_chars} 字。
5. 返回严格 JSON 对象：{{"id": 1, "zh_text": "...", "estimated_seconds": 1.0, "notes": ""}}

segment:
{segment_json}
"""
