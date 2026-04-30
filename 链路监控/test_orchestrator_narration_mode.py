#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "链路监控"))
sys.path.insert(0, str(ROOT / "小程序API提取岗位信息"))
sys.path.insert(0, str(ROOT / "语音生成"))

import orchestrator  # noqa: E402


class OrchestratorNarrationModeTests(unittest.TestCase):
    def test_template_mode_does_not_require_llm_config_when_tts_is_disabled(self) -> None:
        args = argparse.Namespace(
            dry_run=False,
            no_tts=True,
            narration_mode="template",
            llm_api_key="",
            llm_base_url="",
            llm_model="",
            tts_api_key="",
            tts_app_id="",
            tts_http_url="",
            tts_resource_id="",
            tts_voice="",
            tts_format="",
            tts_sample_rate="",
        )

        old_env = {
            key: os.environ.pop(key, None)
            for key in ("DOUBAO_API_KEY", "DOUBAO_LLM_API_KEY", "ARK_API_KEY")
        }
        try:
            llm_config, tts_config = orchestrator._build_configs(args)
        finally:
            for key, value in old_env.items():
                if value is not None:
                    os.environ[key] = value

        self.assertIsNone(llm_config)
        self.assertIsNone(tts_config)


if __name__ == "__main__":
    unittest.main()
