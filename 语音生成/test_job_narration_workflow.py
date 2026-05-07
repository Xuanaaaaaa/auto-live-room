#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_narration_workflow import (  # noqa: E402
    VoiceRequest,
    build_llm_messages,
    build_voice_llm_messages,
    build_danmu_received_result,
    build_narration_result,
    generate_template_voice_script,
    generate_template_script,
    generate_template_spoken_text,
    normalize_job,
)


class TemplateNarrationTests(unittest.TestCase):
    def test_template_uses_fact_fragments_with_target_length(self) -> None:
        job = normalize_job(
            {
                "id": 1,
                "name": "Python后端开发工程师",
                "company_name": "星河科技",
                "city": "杭州",
                "degree": "本科及以上",
                "experience": "1年以上",
                "job_type": "校招",
                "tags": json.dumps(["Python", "数据库", "接口开发"], ensure_ascii=False),
                "recommendedMessage": "岗位方向和你的后端开发意向比较匹配",
            }
        )

        text = generate_template_spoken_text(job)

        self.assertLessEqual(len(text), 115)
        self.assertIn("杭州", text)
        self.assertIn("Python后端开发工程师", text)
        self.assertIn("星河科技", text)
        self.assertIn("页面关键词包括Python、数据库、接口开发", text)

    def test_template_omits_missing_field_noise(self) -> None:
        job = normalize_job(
            {
                "id": 2,
                "name": "产品经理",
                "company_name": "云舟科技",
            }
        )

        text = generate_template_spoken_text(job)

        self.assertIn("产品经理", text)
        self.assertIn("云舟科技", text)
        self.assertNotIn("城市暂未展示", text)
        self.assertNotIn("页面暂未展示薪资", text)
        self.assertIn("页面信息有限", text)

    def test_template_result_keeps_public_narration_shape(self) -> None:
        job = normalize_job(
            {
                "id": 3,
                "name": "QQ音乐公关传播实习生",
                "company_name": "腾讯音乐娱乐集团",
                "city": "深圳",
                "degree": "本科",
                "job_type": "实习",
                "tags": ["公关传播", "内容运营"],
            }
        )

        result = generate_template_script(job)

        self.assertTrue(result.should_play)
        self.assertEqual(result.title, "QQ音乐公关传播实习生")
        self.assertEqual(result.source, "template")
        self.assertIn("公关传播", result.tags)
        self.assertIsInstance(result.risk_tips, list)
        self.assertIn("适合正在看校招或实习的同学重点留意", result.spoken_text)

    def test_llm_prompt_requests_plain_text_not_json(self) -> None:
        job = normalize_job(
            {
                "id": 4,
                "name": "后端开发工程师",
                "company_name": "谊安",
                "city": "北京丰台",
            }
        )

        messages = build_llm_messages(job)
        prompt = "\n".join(message["content"] for message in messages)

        self.assertIn("只输出口播文案本身", prompt)
        self.assertIn("LLM 说“大语言模型”", prompt)
        self.assertIn("不要输出 llm、api、gpt", prompt)
        self.assertNotIn("JSON 输出格式", prompt)
        self.assertNotIn("必须只输出 JSON", prompt)

    def test_llm_text_wrapper_still_builds_metadata(self) -> None:
        job = normalize_job(
            {
                "id": 5,
                "name": "Java开发实习生",
                "company_name": "青禾软件",
                "city": "上海",
                "tags": ["Java", "Spring"],
            }
        )

        result = build_narration_result(
            job,
            "口播文案：现在看到的是上海的Java开发实习生，公司是青禾软件。",
            source="local_llm",
        )

        self.assertEqual(result.source, "local_llm")
        self.assertTrue(result.spoken_text.startswith("现在看到的是上海"))
        self.assertEqual(result.title, "Java开发实习生")
        self.assertEqual(result.tags[:2], ["Java", "Spring"])

    def test_job_found_voice_prompt_can_include_danmu_context(self) -> None:
        job = normalize_job(
            {
                "id": 6,
                "name": "产品经理实习生",
                "company_name": "星河科技",
                "city": "北京",
            }
        )

        messages = build_voice_llm_messages(
            VoiceRequest(
                scene="job_found",
                danmu={"raw_text": "查北京产品经理 本科", "keyword": "产品经理", "city": "北京"},
                job=job,
                search_summary={"count": 8, "returned": 3},
            )
        )
        prompt = "\n".join(message["content"] for message in messages)

        self.assertIn("viewer_query", prompt)
        self.assertIn("查北京产品经理 本科", prompt)
        self.assertIn("search_summary", prompt)
        self.assertIn("产品经理实习生", prompt)

    def test_danmu_received_voice_template_is_short_ack(self) -> None:
        result = generate_template_voice_script(
            VoiceRequest(
                scene="danmu_received",
                danmu={"raw_text": "查北京产品经理 本科", "keyword": "产品经理", "city": "北京", "education": "本科"},
            )
        )

        self.assertTrue(result.should_play)
        self.assertEqual(result.source, "template")
        self.assertIn("产品经理", result.spoken_text)
        self.assertNotIn("你", result.spoken_text)
        self.assertLessEqual(len(result.spoken_text), 80)

    def test_danmu_received_voice_template_has_stable_variants(self) -> None:
        samples = [
            {"raw_text": "查北京产品经理 本科", "keyword": "产品经理", "city": "北京", "education": "本科"},
            {"raw_text": "看看上海前端", "keyword": "前端", "city": "上海"},
            {"raw_text": "搜杭州Java硕士", "keyword": "Java", "city": "杭州", "education": "硕士"},
            {"raw_text": "有没有深圳运营", "keyword": "运营", "city": "深圳"},
        ]

        texts = {
            generate_template_voice_script(
                VoiceRequest(scene="danmu_received", danmu=sample)
            ).spoken_text
            for sample in samples
        }

        self.assertGreaterEqual(len(texts), 3)
        for text in texts:
            self.assertNotIn("你", text)

    def test_danmu_received_result_rewrites_direct_you(self) -> None:
        result = build_danmu_received_result(
            VoiceRequest(
                scene="danmu_received",
                danmu={"raw_text": "查北京产品经理", "keyword": "产品经理", "city": "北京"},
            ),
            "好，我看到有观众想查北京产品经理，马上来帮你找找看。",
            source="doubao",
        )

        self.assertNotIn("你", result.spoken_text)
        self.assertIn("帮这位朋友", result.spoken_text)


if __name__ == "__main__":
    unittest.main()
