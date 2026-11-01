#!/usr/bin/env python3
"""entry_scan.py 的格 —— 这门扫器自己得有反例，否则它就是「永远亮的灯」。

审计器的正控方向是**绿**（喂干净样本必须报 0），负控必须红。
三格：
  1 真仓干净    ⇒ problems 为空（正控，绿）
  2 裸 main()   ⇒ 被点名（负控，红）—— 这就是 assert_trace 那一晚的形状
  3 raise SystemExit ⇒ 不被点名（第一版扫器在这里假阳过一例）
     ★ 第三格是给扫器自己的教训：只认「调用名以 exit 结尾」就是把文本关系
       当控制流关系，`raise SystemExit(main())` 一样兑现了退出码。
"""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "tools"))
import entry_scan  # noqa: E402

BARE = '''
import sys
def main():
    print("rc=9")
    return 9
if __name__ == "__main__":
    main()
'''

RAISED = '''
def main():
    return 9
if __name__ == "__main__":
    raise SystemExit(main())
'''

EXITED = '''
import sys
def main():
    return 9
if __name__ == "__main__":
    sys.exit(main())
'''


def fixture(*sources):
    root = pathlib.Path(tempfile.mkdtemp(prefix="entryscan_"))
    (root / "tools").mkdir()
    for name, body in sources:
        (root / "tools" / name).write_text(body)
    return root


class EntryScan(unittest.TestCase):
    def test_real_repo_is_clean(self):
        """正控：真仓必须零问题，否则这门的绿也不说明什么。"""
        checked, problems = entry_scan.scan(HERE)
        self.assertGreater(checked, 5, "一个都没扫到 —— 扫描面是空的")
        self.assertEqual(problems, [], "真仓里有洞：%s" % problems)

    def test_bare_main_call_is_flagged(self):
        """负控：裸调 main() 必须被点名。这就是 JSON 写 9、进程退 0 的那个形状。"""
        root = fixture(("a.py", BARE))
        checked, problems = entry_scan.scan(root)
        self.assertEqual(checked, 1)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0][0], "a.py")

    def test_systemexit_raise_is_accepted(self):
        """扫器不能在 `raise SystemExit(main())` 上假阳——那是它的第一版。"""
        root = fixture(("b.py", RAISED), ("c.py", EXITED))
        checked, problems = entry_scan.scan(root)
        self.assertEqual(checked, 2)
        self.assertEqual(problems, [], "把兑现了退出码的两种写法判成没出口")

    def test_exit_code_of_the_scanner_itself(self):
        """扫器自己的进程 rc：有洞 ⇒ 1，没洞 ⇒ 0。别让它自己犯它查的病。"""
        clean = entry_scan.main(["entry_scan.py", str(fixture())])
        dirty = entry_scan.main(["entry_scan.py", str(fixture(("a.py", BARE)))])
        self.assertEqual((clean, dirty), (0, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
