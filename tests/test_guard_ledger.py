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


class ReadSideReconcileTest(_LedgerCase):
    """读侧对账 —— 围炉 #34 seq 4413 §四 那三格（L9/L10/L11）的对应物。

    ★ 这一组特意包含**一格证明它抓不到什么**：没有那一格，
      一次全绿会被读成「台账不会丢行」。
    """

    def _write(self, n):
        for i in range(n):
            L.note("g", "refused", "第 %d 发" % i)

    def test_write_read_counts_match(self):
        self._write(12)
        v = L.verify(self.p)
        self.assertEqual((v["lines"], v["parsed"], v["bad"], v["tail_ok"]),
                         (12, 12, 0, True))
        self.assertTrue(v["consistent"])

    def test_truncated_tail_is_counted_not_dropped(self):
        """末行被截断：坏行 1 必须印出来。★ 不印数 = 兜底不存在。"""
        self._write(12)
        raw = open(self.p, "rb").read()
        open(self.p, "wb").write(raw[:-10])
        v = L.verify(self.p)
        self.assertEqual(v["bad"], 1)
        self.assertFalse(v["tail_ok"])
        self.assertFalse(v["consistent"])
        # 旧的 load() 会把这一行 continue 掉，读起来像「本来就 11 发」
        self.assertEqual(len(L.load(self.p)), 11)

    def test_main_refuses_when_bad_lines_present(self):
        self._write(3)
        raw = open(self.p, "rb").read()
        open(self.p, "wb").write(raw + b"{not json}\n")
        self.assertEqual(L.main(), 3)

    def test_whole_line_loss_is_NOT_detectable(self):
        """★ 这格不测「能抓到」，测「抓不到」——丢一整行时，行数自洽、坏行 0。

        所以这张表永远不能说「没丢」；要说「没丢」得有一个台账之外的数
        （像 knife_run 的 10 把刀那样）。这格存在的意义是让那个限制不被忘掉。
        """
        self._write(5)
        lines = open(self.p, "rb").read().split(b"\n")
        open(self.p, "wb").write(b"\n".join(lines[:2] + lines[3:]))  # 掐掉中间一整行
        v = L.verify(self.p)
        self.assertEqual((v["lines"], v["parsed"], v["bad"], v["tail_ok"]),
                         (4, 4, 0, True))
        self.assertTrue(v["consistent"])   # ← 丢了 1 行，账上一切正常


class WriteFailureAndRetentionTest(_LedgerCase):
    """我 4418 给 CZ 讲的两样，先落在自己仓里（不然就是「下次注意」）。

    ①写失败不许被 `except: pass` 吞掉 —— 没进账与没发生在表上同形
    ②归档必须自述 —— 归档之后剩下的行看起来就是「本来只有这么多」，
      归档与丢行在读侧同形
    """

    def setUp(self):
        super().setUp()
        L._WRITE_FAILURES.clear()

    def test_write_failure_is_not_silent(self):
        """★ 这条对应我自己那句「写失败的出口必须 rc≠0」。改之前是 except: pass。"""
        os.environ["HAND_GUARD_LEDGER"] = "/proc/nope/x.jsonl"   # 写不进去
        L.note("g", "ran", "这一发会丢")
        self.assertEqual(len(L._WRITE_FAILURES), 1)
        self.assertIn("FileNotFoundError", L._WRITE_FAILURES[0])
        self.assertEqual(L.main(), 4)                             # 表会偏小 ⇒ rc 非 0

    def test_successful_write_leaves_no_failure_record(self):
        L.note("g", "ran", "正常")
        self.assertEqual(L._WRITE_FAILURES, [])
        self.assertEqual(L.main(), 0)

    def test_prune_moves_oldest_and_leaves_a_receipt(self):
        for i in range(30):
            L.note("g", "ran", "第 %d 发" % i)
        r = L.prune(keep=10, path=self.p)
        self.assertEqual(r["archived"], 20)
        recs, bad, lines = L.load_checked(self.p)
        self.assertEqual((lines, bad), (11, 0))          # 10 保留 + 1 自述
        self.assertTrue(os.path.exists(self.p + ".archive"))
        with open(self.p + ".archive", encoding="utf-8") as f:
            self.assertEqual(len([ln for ln in f.read().split("\n") if ln.strip()]), 20)
        receipts = [x for x in recs if x.get("guard") == "_ledger"]
        self.assertEqual(len(receipts), 1)
        self.assertIn("归档 20 行", receipts[0]["detail"])

    def test_receipt_keeps_table_from_reading_it_as_a_gate(self):
        """自述行不许被当成一道闸（否则表里凭空多出一道「已响过 0 的门」）。"""
        for i in range(5):
            L.note("g", "refused", "x")
        L.prune(keep=2, path=self.p)
        guards = [row[0] for row in L.table(L.load(self.p))]
        self.assertEqual(guards, ["g"])

    def test_archived_rows_are_not_counted_as_lost(self):
        """归档之后对账仍自洽 —— 因为自述行说明了少掉的那些去哪了。"""
        for i in range(20):
            L.note("g", "refused", "x")
        L.prune(keep=5, path=self.p)
        v = L.verify(self.p)
        self.assertTrue(v["consistent"])
        self.assertEqual(v["lines"], 6)


class WiringIsATestNotAClaimTest(unittest.TestCase):
    """★ 「装上了」的唯一读数：它自己在活路径上留下过一行。

    2026-11-01T20:1xZ 撞到的：knife_run 的 import 兜底是一个静默 no-op，
    直接跑脚本时 tools 不在 sys.path 上 ⇒ guard_note 啥也不做，
    台账里从来没有 knife_run 这道闸。表看起来很干净，因为我只核了在场的那两行，
    没问「应该在场的那行为什么不在」。
    """

    def test_knife_run_ledger_import_is_wired(self):
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        sys.path.insert(0, root)
        import importlib
        kr = importlib.import_module("tools.knife_run")
        self.assertTrue(getattr(kr, "_LEDGER_WIRED", False),
                        "knife_run 的台账 import 退化成 no-op 了——这一发不会进账")

    def test_fallback_is_not_silent(self):
        """兜底可以存在，但不许是 pass。源码里出现裸 no-op 兜底就红。"""
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        with open(os.path.join(root, "tools", "knife_run.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("def guard_note(*a, **k):\n        pass", src)
        self.assertIn("台账未接线", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
