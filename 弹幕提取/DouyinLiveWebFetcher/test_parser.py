#!/usr/bin/python
# coding:utf-8
"""
弹幕解析交互测试脚本

在不连真实直播间的情况下，手动输入文本模拟弹幕，立即查看解析结果。
命中的查询会按相同的 JSONL 格式落到 output/ 目录，方便核对下游消费。

用法:
    python test_parser.py              # 纯规则模式
    python test_parser.py --llm        # 启用 LLM 兜底（需先在 LLM_CONFIG 填 API key）
    python test_parser.py --no-output  # 只看终端结果，不写 JSONL
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '弹幕分析脚本'))
from danmaku_parser import DanmakuParser, is_noise


def main():
    ap = argparse.ArgumentParser(description='弹幕解析交互测试')
    ap.add_argument('--llm', action='store_true', help='启用 LLM 兜底')
    ap.add_argument('--no-output', action='store_true', help='不写 JSONL 文件')
    args = ap.parse_args()

    parser = DanmakuParser(enable_llm=args.llm, dedup_ttl=60)

    output_fp = None
    output_path = None
    if not args.no_output:
        os.makedirs('output', exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join('output', f'test_{ts}.jsonl')
        output_fp = open(output_path, 'a', encoding='utf-8', buffering=1)

    print('=' * 60)
    print('  弹幕解析交互测试')
    print('=' * 60)
    print(f"  LLM 兜底:   {'启用' if args.llm else '关闭'}")
    print(f"  JSONL 输出: {output_path or '(已关闭)'}")
    print('  指令:       quit / exit / q  退出')
    print('              stats             查看统计')
    print('=' * 60)

    while True:
        try:
            text = input('弹幕> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in ('quit', 'exit', 'q'):
            break
        if text.lower() == 'stats':
            parser.print_stats()
            continue

        if is_noise(text):
            parser.parse(text)
            print('  [NOISE] 噪声过滤')
            print()
            continue

        result = parser.parse(text)
        if result is None:
            print('  [MISS]  未命中（或在去重窗口内）')
            print()
            continue

        fields = [f"岗位={result.keyword}"]
        if result.city:       fields.append(f"城市={result.city}")
        if result.industry:   fields.append(f"行业={result.industry}")
        if result.salary:     fields.append(f"薪资={result.salary}")
        if result.experience: fields.append(f"经验={result.experience}")
        if result.education:  fields.append(f"学历={result.education}")
        if result.graduate_time: fields.append(f"毕业年份={result.graduate_time}")
        print(f"  [HIT]   命中 [{result.source}]")
        print(f"          {', '.join(fields)}")

        if output_fp:
            record = {
                'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'live_id': 'test',
                'user_id': 'test',
                'user_name': 'tester',
                **{k: v for k, v in asdict(result).items() if k != 'raw_text'},
                'raw_text': result.raw_text,
            }
            output_fp.write(json.dumps(record, ensure_ascii=False) + '\n')
            print(f"          -> {output_path}")
        print()

    if output_fp:
        output_fp.close()
    parser.print_stats()
    if output_path:
        print(f"JSONL 输出: {output_path}")


if __name__ == '__main__':
    main()
