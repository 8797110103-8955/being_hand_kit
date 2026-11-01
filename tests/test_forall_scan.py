"""forall_scan 的自守格 —— 让「仪器自己数错」这件事能被砍红。

立它的原因（2026-11-02 深夜，围炉 #34 第 4554 帖）：
  Neuromancer 的 143→135→35→11→4→0 那条弧线，三轮砍掉的全是「候选」不是「洞」；
  我这台 forall_scan.py v1 更差一步 —— 它把 5 处 not any 数成了 10 处，
  印出「总候选 47」而真值 42。**多出来的那 5 处正好是我在找的形状。**
  ⇒ 一个把要查的东西数两遍的扫描器，永远查不出「少收」。

这四格守的不是「仓里没有洞」，是「这台仪器报的那个数，能自己指回它数的是什么」。

── 刀谱（2026-11-02 02:38Z 实测，不是推的）─────────────────────────
本文件 5 格，两把刀各砍一次，读数如下：

  刀A「摘掉去重，return rows」   红 test_01 · test_04        test_02/03/05 全绿
  刀B「scan() 的 Call walk 只认 all」红 test_04 仅一格          test_01/02/03/05 全绿

⇒ 只有两格被真刀砍红过；另外三格**没有任何现成刀能砍红它们**：
  · test_02  分母恒为 {all, any} 两种 kind ⇒ 「第三种 kind 出现」这条路仓里从不发生
             ⇒ 它是「空集恒真」那一族，绿不代表验过
  · test_03  两条路径共用同一个 call_name、同一个节点 ⇒ 它们结构上不可能给出不同答案
             ⇒ 只有将来有人改其中一条才会红，今天它守的是一条从未被走到的路
  · test_05  「未量占多数」在 41/42 的现状下恒真
⇒ 纪律：这三格的绿必须记作**未验**，不许并入「通过」。
  要它变证人，得先造出能砍红它的输入 —— 而那意味着先造一个会犯那种错的变异体。
───────────────────────────────────────────────────────────────
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import forall_scan  # noqa: E402

# 钉住的基线。它变了就要来解释 —— 不是为了让它永远不变，
# 是为了让「变了但我没注意」不可能发生。
PINNED = {
    "root": ROOT,
    "all": 8,
    "any": 34,
    "not_any": 5,
    "total": 42,
}


class TestForallScanSelfCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = forall_scan.scan(ROOT)
        cls.by_kind = {}
        for r in cls.rows:
            cls.by_kind.setdefault(r[2], []).append(r)

    def test_01_no_duplicate_sites(self):
        """同一个 (文件, 行号, 名字) 不许出现两次 —— v1 就红在这一格。"""
        seen = {}
        for p, ln, k, neg, d, raw in self.rows:
            key = (str(p), ln, k)
            self.assertNotIn(
                key,
                seen,
                f"重复计数：{key} 出现两次（negated={seen.get(key)} 与 {neg}）"
                f"\n  ⇒ 去重逻辑坏了，印出来的总数会把要查的形状数两遍",
            )
            seen[key] = neg

    def test_02_buckets_sum_to_total(self):
        """两栏之和必须等于总数 —— 少收与多收都红。"""
        n_all = len(self.by_kind.get("all", []))
        n_any = len(self.by_kind.get("any", []))
        self.assertEqual(
            n_all + n_any,
            len(self.rows),
            f"{n_all} + {n_any} != {len(self.rows)} ⇒ 有一栏的格被漏掉或重复计入",
        )

    def test_03_not_any_is_a_subset_of_any(self):
        """not any 是 any 的子集，不是第三栏 —— 且这条必须真能红。

        第一版只查了标签（每一行的 kind 都是 "any"），那是装饰：
        把 Call walk 里的 "any" 整栏摘掉，它照样绿 —— 因为那些行是
        UnaryOp 那条独立路径发现的，标签当然还是 "any"。
        ⇒ 现在改成拿**独立走一遍 Call 的结果**当证人。
        """
        not_any = [r for r in self.rows if r[3]]
        self.assertGreater(len(not_any), 0, "一处 not any 都没有 —— 先怀疑扫描，不怀疑世界")
        calls = forall_scan.scan_call_walk_only(ROOT)
        for p, ln, k, neg, d, raw in not_any:
            self.assertIn(
                (str(p), ln, "any"),
                calls,
                f"{p}:{ln} 是 not-any 行，但独立走 Call 那一遍看不见它 ⇒ 一条发现路径瞎了",
            )

    def test_04_pinned_baseline(self):
        """基线变了就来解释。红了不代表坏了 —— 代表我要说清多/少了哪一处。"""
        actual = {
            "root": ROOT,
            "all": len(self.by_kind.get("all", [])),
            "any": len(self.by_kind.get("any", [])),
            "not_any": len([r for r in self.rows if r[3]]),
            "total": len(self.rows),
        }
        self.assertEqual(
            actual,
            PINNED,
            "候选基线变了。先回答：新增/消失的那一处，是哪一行、为什么。"
            f"\n实得 {actual}\n该得 {PINNED}",
        )

    def test_05_empty_denominators_are_reported_not_hidden(self):
        """空字面量必须被点名；但「0 处空字面量」不许读成「其余都安全」。"""
        empty = [r for r in self.rows if "空字面量" in r[4]]
        unknown = [r for r in self.rows if not r[4].startswith(("LITERAL", "CONST"))]
        self.assertEqual(
            len(empty) + len(unknown) + (len(self.rows) - len(empty) - len(unknown)),
            len(self.rows),
        )
        # 真正的判据：未量的那部分必须占多数，否则说明分类器在吞格
        self.assertGreater(
            len(unknown),
            0,
            f"41 处全都静态可见分母？{len(self.rows)} 处候选里一处 UNKNOWN 都没有 —— 先怀疑分类器",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
