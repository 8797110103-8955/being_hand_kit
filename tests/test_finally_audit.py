#!/usr/bin/env python3
"""finally_audit.py 的格 —— 纸面检查（2026-11-01T20:4xZ）第 3 道。

这道装置此前也零测试。纸面结论：**它的 rc 语义是对的**——
rc 报的是「这份读数可不可用」（0 完整 / 2 有读不到 / 3 门响拒绝出数），
不是「结论好不好」。这比「rc=0 就当没事」健康，值得钉住。

钉的三件事：
 ① 门响（rc=3）时**不许印任何读数**——「拒绝出数」与「出了一份 0」必须不同形；
 ② 两个不同的 rc=3 结局（路径不存在 / 树里没有 .py）在 rc 上合并，
    **必须在文本里各自具名**（rc 抹平，文本不许抹平）；
 ③ 正常树 rc=0，且 rc=0 的意思是「读完整了」，脚本自己把它写在那儿。
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "finally_audit.py")


def run(path):
    p = subprocess.run([sys.executable, TOOL, path], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class GateRefusesToPrintReadingsTest(unittest.TestCase):
    def test_nonexistent_path_is_rc_3_and_prints_no_readings(self):
        rc, out = run("/nonexistent/really/not/here")
        self.assertEqual(rc, 3, out)
        self.assertIn("[GATE]", out)
        self.assertNotIn("rc=0", out)

    def test_empty_tree_is_rc_3(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = run(d)
            self.assertEqual(rc, 3, out)
            self.assertIn("[GATE]", out)
            self.assertNotIn("rc=0", out)


class TwoRc3EndingsMustBeNamedInTextTest(unittest.TestCase):
    """rc 合并是允许的，前提是文本里各自具名——这是判据，不是宽容。"""

    def test_missing_path_and_empty_tree_read_differently(self):
        _, a = run("/nonexistent/xyz")
        with tempfile.TemporaryDirectory() as d:
            _, b = run(d)
        self.assertNotEqual(a, b, "两个 rc=3 结局的文本逐字相同 ⇒ 那格在抹平")
        self.assertIn("不是目录", a)
        self.assertIn("一个 .py 都没有", b)


class NormalTreeReadsCleanTest(unittest.TestCase):
    def test_rc_0_means_complete_reading(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.py"), "w", encoding="utf-8") as fh:
                fh.write("def f():\n    try:\n        pass\n    finally:\n        pass\n")
            rc, out = run(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("rc=0", out)
            self.assertIn("读数完整", out)


if __name__ == "__main__":
    unittest.main()
