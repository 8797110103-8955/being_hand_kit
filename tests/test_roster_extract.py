"""roster_extract.py 的自证：合成 raw，真值是我构造的常数。

为什么要这一格（2026-11-01）：这个工具今晚修了三次，两次返工栽在同一处——
我拿脑子里的「正常形状」当 raw 的形状。每次把我拉回来的都是 runner 汇总行，
可汇总行只给总数，给不出「哪一格是哪一格」。所以这里造一份 raw：
每一格的状态是我写进去的、事先知道的常数，工具的名单必须与这些常数相等。
这不是「让它在我造的世界上工作」——它是「让它在我今晚真实失败过的那些形状上工作」：
状态词被 print 顶走、状态词独占一行、正文里含 skipped 字样、同名不同模块。

判据两侧都测：
  正向：真值与构造相符 → rc=0
  负向：①汇总行被改 → rc=1（不能绿）
        ②没有汇总行 → rc=2（没有第二读数，不能判绿）

②这一格是真空绿守卫：若工具在「找不到汇总行」时仍然印 ALL EQUAL，
那么它在任何装置失能的情形下都会通过。
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

TOOL = os.environ.get("ROSTER_TOOL") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools",
    "roster_extract.py",
)
# ROSTER_TOOL 允许指向一份被拨坏的副本，用来验这几格有没有杀伤力：
# 一格只有在「装置坏掉时它会红」时才算护栏，不然它只是描述当前实现。 

# 8 格，真值由构造决定：ok=6 / skip=1 / error=1 / total=8，唯一名字 7（test_dup 同名两模块）
RAW = """\
test_alpha (tests.test_syn.A) ... ok
test_beta (tests.test_syn.A) ... ok
test_print_push (tests.test_syn.A) ... 这一行是测试自己 print 的，状态词被顶到下一行
ok
test_body_word (tests.test_syn.A) ... 注意：这条测试正文里提到 skipped 这个词
ok
test_gamma (tests.test_syn.B) ... skipped 'Chrome unavailable'
test_dup (tests.test_syn.C) ... ok
test_dup (tests.test_syn.D) ... ok
test_delta (tests.test_syn.B) ... ERROR

======================================================================
ERROR: test_delta (tests.test_syn.B)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_syn.py", line 7, in test_delta
    raise ConnectionRefusedError(111, "Connection refused")
ConnectionRefusedError: [Errno 111] Connection refused

----------------------------------------------------------------------
Ran 8 tests in 0.012s

FAILED (errors=1, skipped=1)
"""

TRUE = {"total": 8, "ok": 6, "skip": 1, "error": 1, "fail": 0}


def run_tool(raw_text):
    fd, path = tempfile.mkstemp(suffix=".raw.txt", text=True)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(raw_text)
        p = subprocess.run(
            [sys.executable, TOOL, path],
            capture_output=True, text=True, timeout=120,
        )
        return p.returncode, p.stdout + p.stderr
    finally:
        os.unlink(path)


def parse(out):
    """从 stdout 里读回工具自己的读数（断言不碰内部实现，只看它印了什么）。"""
    total = re.search(r"roster total = (\d+)", out)
    unique = re.search(r"unique names: (\d+)", out)
    counts = {}
    for name, n in re.findall(r"^\s+(ok|skip|error|fail|other|UNKNOWN)\s+= (\d+)$", out, re.M):
        counts[name] = int(n)
    return {
        "total": int(total.group(1)) if total else None,
        "unique": int(unique.group(1)) if unique else None,
        "counts": counts,
    }


class RosterExtractTest(unittest.TestCase):

    def test_positive_roster_equals_constructed_truth(self):
        rc, out = run_tool(RAW)
        got = parse(out)
        self.assertEqual(rc, 0, f"rc={rc} 应为 0\n{out}")
        self.assertIn("ALL EQUAL", out, out)
        self.assertEqual(got["total"], TRUE["total"], f"total\n{out}")
        self.assertEqual(got["unique"], 7, f"唯一名字应为 7（test_dup 同名两模块）\n{out}")
        for k in ("ok", "skip", "error", "fail"):
            self.assertEqual(got["counts"].get(k, 0), TRUE[k], f"{k}\n{out}")

    def test_status_word_pushed_off_and_alone_on_line(self):
        """状态词被 print 顶走、且独占一行时仍认得出——今晚第一次返工的病灶。"""
        rc, out = run_tool(RAW)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("未判出状态", out, f"不该有 UNKNOWN 格\n{out}")

    def test_duplicate_names_in_different_modules_both_collected(self):
        """按名字去重会吞掉同名的第二格（total 会变 7）——今晚第二次返工的病灶。"""
        rc, out = run_tool(RAW)
        self.assertEqual(rc, 0, out)
        self.assertEqual(parse(out)["total"], 8, out)

    def test_body_containing_skipped_is_not_read_as_skip(self):
        """正文里出现 skipped 字样，不能被当成状态词。"""
        rc, out = run_tool(RAW)
        self.assertEqual(rc, 0, out)
        self.assertEqual(parse(out)["counts"].get("skip", 0), 1, out)

    def test_negative_summary_disagrees_must_not_be_green(self):
        """第二读数不同意时不能绿——包括它只差一个数。"""
        rc, out = run_tool(RAW.replace("Ran 8 tests", "Ran 9 tests"))
        self.assertEqual(rc, 1, f"汇总行被改后 rc={rc}，必须为 1\n{out}")
        self.assertIn("MISMATCH", out, out)
        self.assertNotIn("ALL EQUAL", out, out)

    def test_negative_no_summary_cannot_be_green(self):
        """没有第二读数 → rc=2，绝不能印 ALL EQUAL（真空绿守卫）。"""
        raw = RAW.split("Ran 8 tests")[0]
        rc, out = run_tool(raw)
        self.assertEqual(rc, 2, f"没有汇总行时 rc={rc}，必须为 2\n{out}")
        self.assertNotIn("ALL EQUAL", out, out)


if __name__ == "__main__":
    unittest.main()
