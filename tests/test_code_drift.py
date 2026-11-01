"""code_drift 的自证：合成目录树，真值是我构造的常数。

为什么要这一格（2026-11-01）：
    活体 install 上量到——进程 10-27 16:56 启动，12 个 .py 在那之后变过，
    而 health 回执是全绿（alive / 0.13.7 / manifest ok / 无 fork）。
    五个词都是真的，合起来是「我信的路径背后可能是五天前的代码」。
    根因：hand_version 是 import 时读到的字面量，manifest 每次重读，
    两个都是盘上的字；没有一个是跑着的代码的指纹。

    这一格守的是 `_code_drift()` 的分辨率，不是被测代码的正确性：
      - 改了内容 ⇒ 进 changed
      - 新文件 ⇒ 进 added
      - 删文件 ⇒ 进 missing
      - 内容没变（只碰 mtime）⇒ 不许进 changed
      - 空目录 ⇒ 三个都空，不抛

    最后一条是真空绿守卫：_code_drift() 在没有变化时必须给空表，
    而不是给「读不到所以看起来没变」。所以另有一格造 unreadable。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from kit import mcp_server as M
except Exception as e:  # pragma: no cover - environment without mcp dep
    raise unittest.SkipTest(f"mcp_server not importable here: {type(e).__name__}: {e}")


def _mk(base, rel, text):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class TestCodeDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="codedrift_")
        _mk(self.tmp, "hand/a.py", "A = 1\n")
        _mk(self.tmp, "kit/b.py", "B = 2\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 1 真值：a.py 内容变了 -> changed 里有它，且只有它
    def test_changed_file_is_named(self):
        start = M._code_snapshot(self.tmp)
        _mk(self.tmp, "hand/a.py", "A = 999\n")
        ch, ad, gone = M._code_drift(self.tmp, at_start=start)
        self.assertEqual(ch, ["hand/a.py"])
        self.assertEqual(ad, [])
        self.assertEqual(gone, [])

    # 2 新文件与删除各进各的栏，不许混成一个「不一样」
    def test_added_and_missing_are_separate_columns(self):
        start = M._code_snapshot(self.tmp)
        _mk(self.tmp, "hand/new.py", "N = 1\n")
        os.remove(os.path.join(self.tmp, "kit/b.py"))
        ch, ad, gone = M._code_drift(self.tmp, at_start=start)
        self.assertEqual((ch, ad, gone), ([], ["hand/new.py"], ["kit/b.py"]))

    # 3 只碰 mtime、内容没变 -> 不许报 changed
    #    这一格防的是「用 mtime 当指纹」——那是我上一版打算走的错路。
    def test_mtime_only_touch_is_not_drift(self):
        start = M._code_snapshot(self.tmp)
        p = os.path.join(self.tmp, "hand/a.py")
        os.utime(p, (0, 4102444800))  # far future mtime, same bytes
        ch, ad, gone = M._code_drift(self.tmp, at_start=start)
        self.assertEqual((ch, ad, gone), ([], [], []))

    # 4 真空绿守卫：没有变化时必须给三个空表，不是给 None
    def test_no_change_is_three_empty_lists(self):
        start = M._code_snapshot(self.tmp)
        ch, ad, gone = M._code_drift(self.tmp, at_start=start)
        self.assertEqual((ch, ad, gone), ([], [], []))

    # 5 __pycache__ 不许被当成代码（否则每跑一次就报一次 drift）
    def test_pycache_is_ignored(self):
        _mk(self.tmp, "hand/__pycache__/a.cpython-311.pyc", "junk")
        _mk(self.tmp, "hand/__pycache__/x.py", "X = 1\n")
        snap = M._code_snapshot(self.tmp)
        self.assertNotIn("hand/__pycache__/x.py", snap)
        self.assertIn("hand/a.py", snap)

    # 6 读不到的文件要留一个字，不许静默消失（否则删除与不可读同形）
    def test_unreadable_file_keeps_a_word(self):
        start = M._code_snapshot(self.tmp)
        p = os.path.join(self.tmp, "hand/a.py")
        os.chmod(p, 0o000)
        try:
            if os.access(p, os.R_OK):  # running as root: can't simulate
                self.skipTest("running as root, chmod 000 stays readable")
            ch, _ad, _gone = M._code_drift(self.tmp, at_start=start)
            self.assertIn("hand/a.py", ch)
        finally:
            os.chmod(p, 0o644)


if __name__ == "__main__":
    unittest.main(verbosity=2)
