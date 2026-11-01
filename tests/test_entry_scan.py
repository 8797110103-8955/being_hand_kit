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
        """正控：真仓必须零洞。★ 分母为零的正控和没有正控同形（Neuromancer P1
        的「不是全丢」）—— 所以下面还要断 checked 不是 0，光 problems==[] 不算。"""
        seen, checked, problems, suspects = entry_scan.scan(HERE)
        self.assertGreater(checked, 5, "一个都没扫到 —— 扫描面是空的")
        self.assertEqual(problems, [], "真仓里有洞：%s" % problems)
        self.assertEqual(suspects, [], "真仓里有疑，看一眼是不是我判粗了：%s" % suspects)

    def test_bare_main_call_is_flagged(self):
        """负控：裸调 main() 必须被点名。这就是 JSON 写 9、进程退 0 的那个形状。"""
        root = fixture(("a.py", BARE))
        seen, checked, problems, suspects = entry_scan.scan(root)
        self.assertEqual(checked, 1)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(problems[0][0], "a.py")
        self.assertEqual(suspects, [], "有入口块却不在洞里 —— 档位串了")

    def test_systemexit_raise_is_accepted(self):
        """扫器不能在 `raise SystemExit(main())` 上假阳——那是它的第一版。"""
        root = fixture(("b.py", RAISED), ("c.py", EXITED))
        seen, checked, problems, suspects = entry_scan.scan(root)
        self.assertEqual(checked, 2)
        self.assertEqual(problems, [], "把兑现了退出码的两种写法判成没出口")

    def test_bare_main_call_is_a_hole(self):
        """★ 这一档是实仓长出来的样本，不是我编的：tests/live 里三个探针有 main()、
        无入口块、**在模块顶层裸调 main()**。它们跑得起来 —— 我原以为「没有退出码」，
        实际是 rc 恒 0（里面成不成立都不影响 $?），而且 import 它就执行（live_dpr_old_ab
        导入 live_dpr_once 的 HTML 常量，会把整个探针跑一遍）。
        判据：**「没有退出码」和「rc 恒 0」不是一回事，后者看起来正常工作。**"""
        root = fixture(("p.py", "def main():\n    return 1\n\n\nmain()\n"))
        seen, checked, problems, suspects = entry_scan.scan(root)
        self.assertEqual(checked, 1)
        self.assertEqual(len(problems), 1, problems)
        self.assertEqual(suspects, [])
        self.assertEqual(entry_scan.main(["entry_scan.py", str(root)]), 1)

    def test_empty_view_is_refused_not_clean(self):
        """★ 视野为空必须红。否则「我没扫到东西」和「我扫完干净」在回执上同形
        （Neuromancer 2026-11-01T21:2x 还我的一条，他的 .bat 扫描器写死了一个文件名）。"""
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "tools").mkdir()
        self.assertEqual(entry_scan.main(["entry_scan.py", str(root)]), 2,
                         "空视野给了 0 —— 它把「没扫到」报成了「干净」")

    def test_view_is_wider_than_tools(self):
        """视野本身要被钉住：只 glob tools/ 时，tests/live 里那三个裸 main() 全在视野外。"""
        self.assertIn("tests/live", entry_scan.VIEWS)
        seen, checked, problems, suspects = entry_scan.scan(HERE)
        self.assertGreater(seen, checked, "视图里除了 tool 还得有别的东西")

    def test_no_entry_block_is_a_suspect_not_a_hole(self):
        """★ 分档的那一格：有 main() 没有 __main__ 块 ⇒ 进「疑」，不进「洞」，
        退出码仍是 0。理由写在这里而不是只写在 commit 里：Hand 里每个 tool 都是
        CLI，所以它看着像洞；但被 import 的模块本来就没有退出码。我**没验过**它是
        过报还是真洞（实仓 0 例），所以它单列、不打断绿 —— 一红就被当噪音关掉，
        那时真洞也一起失守。"""
        root = fixture(("lib.py", "def main():\n    return 9\n"))
        seen, checked, problems, suspects = entry_scan.scan(root)
        self.assertEqual(problems, [], "疑被升格成洞了")
        self.assertEqual(len(suspects), 1, suspects)
        self.assertEqual(entry_scan.main(["entry_scan.py", str(root)]), 0)

    def test_exit_code_of_the_scanner_itself(self):
        """扫器自己的进程 rc：有洞 ⇒ 1，没洞 ⇒ 0。别让它自己犯它查的病。"""
        clean = entry_scan.main(["entry_scan.py", str(fixture(("ok.py", EXITED)))])
        dirty = entry_scan.main(["entry_scan.py", str(fixture(("a.py", BARE)))])
        self.assertEqual((clean, dirty), (0, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
