"""Release test for 0.13.8 — 一个数只读一次，一句「成功」要对得上页面自己的账。

本版几乎全部由 Neuromancer 在自己环境上的四处实测倒逼，四处都是同一个族：
回执说成功、事情没发生。

这里守机制形状（不需要浏览器）：
  * devicePixelRatio 在读它的每一个动作里只读一次，同一个数乘进去再除出来
    （selector / text= / handle / @img 点四条路径）
  * force=true 不是旁路：它要交出见证人，拿不出就拒绝，并说明是哪种拿不出
  * 所有权记录按调用时的端口取文件，不用 import 时刻的模块常量
  * 「够不着端点」与「关闭失败」在回执里是两个词
  * tests/live 的 dpr 验收脚本自己判、自己决定退出码

行为由 tests/test_dpr_single_read.py 与 tests/live/live_text_dpr.py 守。
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _fn_body(name, src=None):
    src = src if src is not None else _read("hand", "action", "cdp_act.py")
    start = src.index("def %s(" % name)
    rest = src[start + 1:]
    m = re.search(r"\ndef ", rest)
    return rest if m is None else rest[:m.start()]


class TestVersion0138(unittest.TestCase):

    def test_version_is_current(self):
        """Newest release test owns the exact current version."""
        self.assertIn('__version__ = "0.13.8"', _read("hand", "__init__.py"))
        self.assertIn('"version": "0.13.8"', _read("kit", "manifest.json"))

    def test_changelog_entry_names_the_changes(self):
        body = _read("CHANGELOG.md")
        self.assertIn("## [0.13.8]", body)
        section = body.split("## [0.13.8]")[1].split("## [")[0]
        for needle in ("devicePixelRatio", "force", "所有权记录", "够不着端点"):
            self.assertIn(needle, section)


class TestDPRSingleRead(unittest.TestCase):

    def test_every_acting_path_reads_dpr_exactly_once(self):
        for fn in ("cdp_click", "cdp_type", "cdp_click_handle", "_point_from_spec"):
            body = _fn_body(fn)
            self.assertEqual(
                body.count("_dpr_now(ws)"), 1,
                "%s must read dpr exactly once, got %d"
                % (fn, body.count("_dpr_now(ws)")))

    def test_receipt_says_how_many_reads(self):
        src = _read("hand", "action", "cdp_act.py")
        self.assertIn("dpr_reads", src)

    def test_text_path_has_its_own_dpr_receipt(self):
        """text= 是 0.13.8 补的第四条腿（前三处在 selector/handle/@img）。"""
        text_body = _fn_body("cdp_click_do")
        self.assertIn("text=", text_body)


class TestForceIsNotABypass(unittest.TestCase):

    def test_force_must_produce_a_witness(self):
        src = _read("hand", "perception", "cdp_launcher.py")
        self.assertIn("force proves intent, not identity", src)
        self.assertIn("the listener on this port carries a different profile", src)

    def test_owner_file_is_read_at_call_time(self):
        src = _read("hand", "perception", "cdp_launcher.py")
        start = src.index("def _owner_file(")
        body = src[start:start + 900]
        self.assertIn("HAND_CDP_OWNER_FILE", body)
        self.assertIn("os.environ.get", body)


class TestUnreachableIsNotFailure(unittest.TestCase):

    def test_close_receipt_separates_the_two(self):
        src = _read("hand", "hand.py")
        self.assertIn('could not reach the endpoint', src)


class TestLiveScriptDecidesItsOwnExit(unittest.TestCase):

    def test_live_dpr_script_judges_and_returns_a_code(self):
        """入口块不等于判据：sys.exit(main()) 守着一个恒返回 None 的函数，
        仍然是 rc 恒 0。这一格守的是「它真的判」。"""
        body = _read("tests", "live", "live_text_dpr.py")
        self.assertIn("verdict:", body)
        self.assertIn("return 0 if", body)
        self.assertIn("sys.exit(main())", body)


if __name__ == "__main__":
    unittest.main()
