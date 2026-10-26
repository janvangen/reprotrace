"""reprotrace —— 自检测试。

记录提示词、参数、输入与环境快照，让同一次生成能被再次跑出来。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reprotrace  # noqa: E402


class TestReproTrace(unittest.TestCase):
    def test_capture_records_fingerprints(self):
        arc = reprotrace.capture({
            "prompt": "你好", "model": "gpt-4o", "params": {"temperature": 0},
            "seed": 42, "inputs": {"q": "你好"}, "output": {"a": "你好"}})
        self.assertEqual(len(arc["inputs_sha256"]), 64)
        self.assertEqual(len(arc["output_sha256"]), 64)

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValueError):
            reprotrace.capture({"prompt": "x", "model": "y"})

    def test_missing_seed_lowers_reproducibility(self):
        arc = reprotrace.capture({"prompt": "x", "model": "y", "params": {}})
        self.assertEqual(arc["reproducibility"]["level"], "low")
        self.assertIn("没有随机种子", arc["reproducibility"]["factors"])

    def test_uncontrollable_factors_are_listed(self):
        arc = reprotrace.capture({"prompt": "x", "model": "y", "params": {}, "seed": 1})
        self.assertTrue(arc["uncontrollable"])
        self.assertTrue(any("权重" in u for u in arc["uncontrollable"]))

    def test_verify_detects_difference(self):
        old = reprotrace.capture({"prompt": "a", "model": "m", "params": {"t": 0},
                              "seed": 1, "inputs": {"x": 1}})
        new = reprotrace.capture({"prompt": "b", "model": "m", "params": {"t": 0},
                              "seed": 1, "inputs": {"x": 1}})
        v = reprotrace.verify(old, new)
        self.assertFalse(v["all_match"])

    def test_verify_detects_match(self):
        payload = {"prompt": "a", "model": "m", "params": {"t": 0},
                   "seed": 1, "inputs": {"x": 1}}
        v = reprotrace.verify(reprotrace.capture(payload), reprotrace.capture(payload))
        self.assertTrue(v["all_match"])
