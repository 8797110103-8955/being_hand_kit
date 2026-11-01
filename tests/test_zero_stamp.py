#!/usr/bin/env python3
"""zero_stamp.py 的格 —— 纸面检查（2026-11-01T20:3xZ）落成读数。

为什么有这个文件：这道装置此前**零测试**（tools_test_coverage 记过：7 个用具里
只有 roster_extract 在 tests/ 有引用）。于我它属于「装上了、从没验过」那一栏。

这组格只问一件事：**四个结局在读数上是否真的分开**。
  同内容 0 / 内容变 4 / 文件没了 5 / 回执解析不了 2
纸面判据不是「代码写没写这条分支」，是「两个不同结局会不会落到同一个值」。
它已经写对了四个值——那就把「写对了」变成一条会红的读数。
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "zero_stamp.py")

RC_SAME, RC_UNPARSABLE, RC_CHANGED, RC_MISSING = 0, 2, 4, 5


def run(*args):
    p = subprocess.run([sys.executable, TOOL] + list(args),
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class FourEndingsMustStayDistinctTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = os.path.join(self.tmp.name, "subject.txt")
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("A = 1\n")
        rc, out = run(self.f)
        assert rc == 0, out
        self.stamp = out.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_is_0(self):
        rc, out = run("--verify", self.stamp)
        self.assertEqual(rc, RC_SAME, out)
        self.assertIn("same", out)

    def test_content_change_is_4(self):
        # 等长替换：长度也变了的话，这一格只在「大小也变了」的世界里被验过
        # （同族教训：2026-11-01 15:45 的 K9 夹具）
        with open(self.f, "w", encoding="utf-8") as fh:
            fh.write("A = 2\n")
        rc, out = run("--verify", self.stamp)
        self.assertEqual(rc, RC_CHANGED, out)
        self.assertIn("changed", out)

    def test_missing_file_is_5_not_same(self):
        os.remove(self.f)
        rc, out = run("--verify", self.stamp)
        self.assertEqual(rc, RC_MISSING, out)
        self.assertIn("missing", out)

    def test_unparsable_is_2_not_missing(self):
        rc, out = run("--verify", "VERIFY 完全不是回执")
        self.assertEqual(rc, RC_UNPARSABLE, out)
        self.assertNotIn("missing", out)

    def test_four_values_are_pairwise_distinct(self):
        self.assertEqual(len({RC_SAME, RC_UNPARSABLE, RC_CHANGED, RC_MISSING}), 4)


class SelftestMustNotBeEmptyGreenTest(unittest.TestCase):
    """selftest 0/0 与 selftest 7/7 在旧版里同一个值（`0 if not bad else 3`）。"""

    def test_selftest_passes(self):
        rc, out = run("--selftest")
        self.assertEqual(rc, 0, out)
        self.assertIn("selftest", out)

    def test_empty_case_list_guard_exists_in_source(self):
        """前置闸：cases 为空必须 rc=9，不许印全过。"""
        with open(TOOL, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("if not cases:", src)
        self.assertIn("0/0 不是全过", src)


if __name__ == "__main__":
    unittest.main()
