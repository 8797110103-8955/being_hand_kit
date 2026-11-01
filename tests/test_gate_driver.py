#!/usr/bin/env python3
"""tools/gate.py 自己的格 —— 驱动侧对账也要被验，否则它就是「谁数我叫过几次」的那个谁。

判据（2026-11-01T21:2xZ）：这一层的价值全在「它能红」。所以四格里有三格是**押红**：

  P1 记账 1 次        → rc=0（对账通过）       ← 基线，不是重点
  N1 记 0 次（忘了）   → rc=9 LEDGER_LOST      ← 重点：这是它存在的理由
  N2 记 2 次          → rc=4 LEDGER_DOUBLED    ← 同一动作记两次，也要叫
  N3 工具崩在记账前    → rc=9 LEDGER_LOST      ← 「崩了」与「没跑」不许同形
  N4 工具不存在        → rc=3 GATE_CRASHED

若 N1/N2/N3 全绿，说明这层只会说「通过」——那它就是装饰，不是护栏。
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WRAPPER = os.path.join(ROOT, "tools", "gate.py")
TOOLS = os.path.join(ROOT, "tools")

FAKE_OK = '''
import sys, os
sys.path.insert(0, %r)
import guard_ledger as L
L.note("fake", "ran", "clean")
sys.exit(0)
''' % TOOLS

FAKE_SILENT = '''
import sys
sys.exit(0)
'''

FAKE_TWICE = '''
import sys, os
sys.path.insert(0, %r)
import guard_ledger as L
L.note("fake", "ran", "a")
L.note("fake", "ran", "b")
sys.exit(0)
''' % TOOLS

FAKE_CRASH = '''
import sys, os
sys.path.insert(0, %r)
import guard_ledger as L
raise RuntimeError("死在记账之前")
''' % TOOLS


class DriverReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gate-driver-")
        self.ledger = os.path.join(self.dir, "ledger.jsonl")
        self.env = dict(os.environ)
        self.env["HAND_GUARD_LEDGER"] = self.ledger
        self.env.pop("HAND_GUARD_RUN_ID", None)

    def _tool(self, src, name="fake_tool.py"):
        p = os.path.join(self.dir, name)
        with open(p, "w") as fh:
            fh.write(src)
        return p

    def _run(self, *args):
        p = subprocess.run([sys.executable, WRAPPER] + list(args),
                           capture_output=True, text=True, env=self.env)
        return p.returncode, p.stdout + p.stderr

    def test_p1_one_note_one_row_passes(self):
        rc, out = self._run(self._tool(FAKE_OK))
        self.assertEqual(rc, 0, out)
        self.assertIn("对账通过", out)

    def test_n1_silent_tool_is_ledger_lost(self):
        """★ 这一格是整层存在的理由：工具跑了、rc=0、但一行没留。"""
        rc, out = self._run(self._tool(FAKE_SILENT, "silent.py"))
        self.assertEqual(rc, 9, out)
        self.assertIn("LEDGER_LOST", out)
        self.assertIn("子进程 rc=0", out)   # ★ 它说没事，却一行没留

    def test_n2_double_note_is_flagged(self):
        rc, out = self._run(self._tool(FAKE_TWICE, "twice.py"))
        self.assertEqual(rc, 4, out)
        self.assertIn("LEDGER_DOUBLED", out)

    def test_n3_crash_before_note_is_ledger_lost(self):
        rc, out = self._run(self._tool(FAKE_CRASH, "crash.py"))
        self.assertEqual(rc, 9, out)
        self.assertIn("LEDGER_LOST", out)
        self.assertIn("RuntimeError", out)
        # 两种「0 行」要分得开：静默成功 vs 崩在记账前——子进程 rc 是那一格
        self.assertIn("子进程 rc=1", out)

    def test_n4_missing_tool_is_crashed_not_out_of_ledger(self):
        """两种红必须分得开：工具起不来 ≠ 工具起来没记账。"""
        rc, out = self._run(os.path.join(self.dir, "does_not_exist.py"))
        self.assertEqual(rc, 3, out)
        self.assertIn("GATE_CRASHED", out)
        self.assertNotIn("LEDGER_LOST", out)

    def test_provenance_flag_reaches_the_row(self):
        rc, _ = self._run("--provenance", "constructed:test", self._tool(FAKE_OK))
        self.assertEqual(rc, 0)
        with open(self.ledger) as fh:
            self.assertIn("constructed:test", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
