#!/usr/bin/env python3
"""guard_ledger 自己的格 —— 台账装置也要被验，否则它就成了「谁问闸响过没有」的新答案里最安静的那一环。

2026-11-01T19:2xZ 追加 provenance 一格（围炉 #34 4409→4413）：
「响过」必须按**来历**拆开——同一栏里「我在自己造的坏世界里验过」与
「真实世界出现过」数值相同、读起来是同一件事。默认 unlabeled：不给「自然」盖章。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import guard_ledger as L  # noqa: E402


class _LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = os.path.join(self.tmp, "ledger.jsonl")
        os.environ["HAND_GUARD_LEDGER"] = self.p
        os.environ.pop("HAND_GUARD_PROVENANCE", None)

    def tearDown(self):
        os.environ.pop("HAND_GUARD_LEDGER", None)
        os.environ.pop("HAND_GUARD_PROVENANCE", None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class GuardLedgerTest(_LedgerCase):
    def test_empty_ledger_has_no_rows(self):
        """空台账必须给空表 —— 而不是给一张「全部正常」的表。"""
        self.assertEqual(L.table(L.load(self.p)), [])

    def test_ran_but_never_fired_is_flagged(self):
        """跑过、一次没响 ⇒ 未验响过。这正是「闸自己没被验」的自动显形。"""
        L.note("g", "ran", "clean")
        L.note("g", "ran", "clean")
        rows = L.table(L.load(self.p))
        self.assertEqual(rows, [("g", 2, 0, None, "未验响过", {})])

    def test_fired_records_last_time(self):
        L.note("g", "ran", "")
        L.note("g", "refused", "基线读数没解析出来")
        g, ran, ref, last, verdict, prov = L.table(L.load(self.p))[0]
        self.assertEqual((ran, ref, verdict), (1, 1, "已响过"))
        self.assertIsNotNone(last)
        self.assertRegex(last, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(prov, {"unlabeled": 1})

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


class ProvenanceTest(_LedgerCase):
    """★ 「响过」按来历拆开（2026-11-01T19:2xZ）。"""

    def test_constructed_vs_unlabeled_are_split(self):
        L.note("g", "refused", "我造的坏运行")
        os.environ["HAND_GUARD_PROVENANCE"] = "constructed:shell"
        L.note("g", "refused", "外壳造的第二发")
        os.environ.pop("HAND_GUARD_PROVENANCE")
        prov = L.table(L.load(self.p))[0][5]
        self.assertEqual(L.prov_split(prov), (1, 1))

    def test_missing_provenance_is_not_labelled_natural(self):
        """没说出来历 ≠ 自然发生。★ 我不给「自然」盖章，只说没见过。"""
        L.note("g", "refused", "没说来历")
        rec = L.load(self.p)[-1]
        self.assertEqual(rec.get("provenance"), "unlabeled")
        self.assertNotIn(rec.get("provenance"), ("natural", "wild", "real"))

    def test_explicit_provenance_argument_wins_over_env(self):
        os.environ["HAND_GUARD_PROVENANCE"] = "constructed:env"
        L.note("g", "refused", "调用点显式给", provenance="constructed:caller")
        self.assertEqual(L.load(self.p)[-1].get("provenance"), "constructed:caller")

    def test_unlabeled_hits_are_reported_separately(self):
        """表上必须能看出「有响过的、来历不明」——那是自然样本的候选清单。"""
        L.note("g", "refused", "来历不明的一发")
        os.environ["HAND_GUARD_PROVENANCE"] = "constructed:shell"
        L.note("h", "refused", "我造的")
        os.environ.pop("HAND_GUARD_PROVENANCE")
        rows = {r[0]: r for r in L.table(L.load(self.p))}
        self.assertEqual(L.prov_split(rows["g"][5]), (0, 1))
        self.assertEqual(L.prov_split(rows["h"][5]), (1, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
