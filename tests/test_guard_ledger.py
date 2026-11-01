#!/usr/bin/env python3
"""guard_ledger 自己的格 —— 台账装置也要被验，否则它就成了「谁问闸响过没有」的新答案里最安静的那一环。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import guard_ledger as L  # noqa: E402


class GuardLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = os.path.join(self.tmp, "ledger.jsonl")
        os.environ["HAND_GUARD_LEDGER"] = self.p

    def tearDown(self):
        os.environ.pop("HAND_GUARD_LEDGER", None)

    def test_empty_ledger_has_no_rows(self):
        """空台账必须给空表 —— 而不是给一张「全部正常」的表。"""
        self.assertEqual(L.table(L.load(self.p)), [])

    def test_ran_but_never_fired_is_flagged(self):
        """跑过、一次没响 ⇒ 未验响过。这正是「闸自己没被验」的自动显形。"""
        L.note("g", "ran", "clean")
        L.note("g", "ran", "clean")
        rows = L.table(L.load(self.p))
        self.assertEqual(rows, [("g", 2, 0, None, "未验响过")])

    def test_fired_records_last_time(self):
        L.note("g", "ran", "")
        L.note("g", "refused", "基线读数没解析出来")
        rows = L.table(L.load(self.p))
        g, ran, ref, last, verdict = rows[0]
        self.assertEqual((ran, ref, verdict), (1, 1, "已响过"))
        self.assertIsNotNone(last)
        self.assertRegex(last, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_two_guards_do_not_merge(self):
        """两闸不许并成一行 —— 合并会让「一道响过」替另一道作证。"""
        L.note("a", "ran", "")
        L.note("b", "refused", "x")
        rows = {r[0]: r for r in L.table(L.load(self.p))}
        self.assertEqual(rows["a"][4], "未验响过")
        self.assertEqual(rows["b"][4], "已响过")

    def test_write_failure_does_not_raise(self):
        """写台账失败不许让闸崩 —— 记账是旁路，不是被判物。"""
        os.environ["HAND_GUARD_LEDGER"] = "/proc/nonexistent/ledger.jsonl"
        L.note("g", "refused", "x")  # 不抛即通过


if __name__ == "__main__":
    unittest.main(verbosity=2)
