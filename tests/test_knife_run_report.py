#!/usr/bin/env python3
"""knife_run 报表纪律的判据格 —— 纯合成数据，不跑真刀集（约 40s/次）。

为什么有这个文件（2026-11-01T18:5xZ）：
我在围炉 #34 说「下一步照纸面检查把自己的闸推一遍」，推的第一下就推出真洞：
`invalid_reasons` 的第一版只查每把刀的行，**没查 clean 基线**——基线的 rc 只被
print 出来、从不参与判断，于是「基线自己崩了」与「基线正常」在报表上是同一个读数。
把判据抽成纯函数后，五种结局都能用合成数据各喂一次，不必等一轮真跑。

★ 第五格是本文件里最要紧的一格：**五种结局的拒绝理由文本必须两两不同。**
  这正是「判据的值域比结局的值域小 ⇒ 抹平」那条律的可执行版本——
  如果两个结局印出同一句话，那格不是在分辨，是在抹平，而且抹平看起来和平稳一样。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import knife_run as K  # noqa: E402

ORIG = "def f():\n    return 1\n"
GOOD = K.sha8(ORIG)


def row(name, rc=0, got=GOOD, landed=True):
    return (name, rc, [], GOOD, got, landed, (), 1)


class InvalidReasonsTest(unittest.TestCase):
    def base(self, rc=0, sha=None):
        return {"rc": rc, "module_sha": GOOD if sha is None else sha}

    def test_clean_run_has_no_reasons(self):
        """正控：一切正常时必须给空 —— 否则这道闸对所有跑都响，等于没有闸。"""
        self.assertEqual(K.invalid_reasons(self.base(), [row("K1"), row("K2")], ORIG), [])

    def test_broken_baseline_is_refused(self):
        """基线崩了与基线正常曾经是同一个读数（新洞，纸面检查推出来的）。"""
        r = K.invalid_reasons(self.base(rc="UNPARSED"), [row("K1")], ORIG)
        self.assertTrue(r and "基线" in r[0], r)

    def test_baseline_reading_wrong_file_is_refused(self):
        """基线读到的是不是我写的那份 —— 与每把刀的 landed 同一件事，对象换成未变异原文。"""
        r = K.invalid_reasons(self.base(sha="deadbeef"), [row("K1")], ORIG)
        self.assertTrue(r and "基线" in r[0], r)

    def test_unparsed_knife_is_refused(self):
        r = K.invalid_reasons(self.base(), [row("K1", rc="UNPARSED", got=None, landed=False)], ORIG)
        self.assertTrue(r and "没解析" in r[0], r)

    def test_not_landed_knife_is_refused(self):
        r = K.invalid_reasons(self.base(), [row("K1", got="00000000", landed=False)], ORIG)
        self.assertTrue(r and "位置" in r[0], r)

    def test_five_endings_have_five_distinct_receipts(self):
        """值域检查：五种结局必须印出五句不同的话。两句相同 ⇒ 那格在抹平。"""
        endings = {
            "clean": K.invalid_reasons(self.base(), [row("K1")], ORIG),
            "base_crash": K.invalid_reasons(self.base(rc="UNPARSED"), [row("K1")], ORIG),
            "base_stale": K.invalid_reasons(self.base(sha="deadbeef"), [row("K1")], ORIG),
            "knife_crash": K.invalid_reasons(self.base(), [row("K1", rc="UNPARSED", landed=False)], ORIG),
            "knife_miss": K.invalid_reasons(self.base(), [row("K1", got="00000000", landed=False)], ORIG),
        }
        texts = [" | ".join(v) for v in endings.values()]
        self.assertEqual(len(set(texts)), len(texts),
                         "有两种结局印出了同一句话：%s" % endings)
        self.assertEqual(endings["clean"], [], "正控必须为空，否则整道闸对所有跑都响")


if __name__ == "__main__":
    unittest.main(verbosity=2)
