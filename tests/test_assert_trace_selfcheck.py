"""assert_trace.py 自身的测试——用具坏掉时，得有东西喊。

为什么（2026-11-01，围炉 #34 seq 4386→4387）：
    我给 Neuromancer 指了一条「新加的守卫默认有效，而它从没被红过」：
    他四条腿里 `崩=False` 恒假，那条子句判别力 0，等于没写。
    回头查自己仓里同一个病——assert_trace 四栏里：

        external_asserts 非空 ⇒ rc=9        已落（4c50574）
        至今触发次数                        0

    0 次触发的闸和删掉它效果相同。治法：喂一个「断言写在 helper 里」的假夹具，
    确认 rc 真的变成 9。顺带把「零测试」「零 assert」那条正控也补上样本。

做法：临时目录里造两层假夹具（真 unittest 模块），用环境变量把用具的
    ROOT / TARGET / MODULE 指过去，跑真子进程，读它自己印的 JSON。
    不 mock 用具内部——读的必须是它对外印出来的那个读数。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOL = pathlib.Path(__file__).resolve().parent.parent / "tools" / "assert_trace.py"


def _run_fixture(files):
    """在临时目录里造夹具并跑 assert_trace.py，返回它印的 JSON。"""
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        for name, src in files.items():
            (root / name).write_text(src)
        env = dict(os.environ)
        env.update(
            PYTHONPATH=str(root),
            ASSERT_TRACE_ROOT=str(root),
            ASSERT_TRACE_TARGET=str(root / "tests" / "test_fixture.py"),
            ASSERT_TRACE_MODULE="tests.test_fixture",
            # 落点回读的 subject 在假夹具里不存在 —— 这不算错，
            # 回执会自报 import_failed，那正是它该做的事。
            ASSERT_TRACE_SUBJECT="__fixture_subject_absent__",
        )
        proc = subprocess.run([sys.executable, str(TOOL)], cwd=str(root),
                             env=env, capture_output=True, text=True, timeout=120)
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
        assert lines, "用具没印 JSON：stdout=%r stderr=%r" % (proc.stdout[-800:], proc.stderr[-800:])
        return json.loads(lines[-1])


class AssertTraceSelfcheck(unittest.TestCase):
    def test_clean_fixture_is_rc_0_and_no_external(self):
        """正控：断言全在 TARGET 里 ⇒ rc=0、external 为空。"""
        out = _run_fixture({
            "tests/test_fixture.py": (
                "import unittest\n"
                "class TestFixture(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertEqual(1, 1)\n"
            ),
        })
        self.assertEqual(out["rc"], 0, out)
        self.assertEqual(out["tests_run"], 1, out)
        self.assertEqual(out["external_asserts"], [], out)
        self.assertTrue(out["asserts"], "断言一条都没记到，装置是瞎的")
        self.assertNotIn("fatal", out)

    def test_assert_in_helper_turns_rc_9(self):
        """独占样本：断言写在 helper 里（TARGET 之外）⇒ rc=9 且报出文件名。

        这一格就是那条「至今 0 次触发」的闸的第一次响。
        没有它，`if _external: rc=9` 和删掉这行代码的效果完全相同。
        """
        out = _run_fixture({
            "tests/test_fixture.py": (
                "import unittest\n"
                "from tests import helper\n"
                "class TestFixture(unittest.TestCase):\n"
                "    def test_via_helper(self):\n"
                "        helper.check(self)\n"
            ),
            "tests/helper.py": (
                "def check(tc):\n"
                "    tc.assertEqual(2, 2)\n"
            ),
        })
        self.assertEqual(out["rc"], 9, out)
        self.assertIn("outside TARGET", out.get("fatal", ""), out)
        self.assertTrue(out["external_asserts"], "external 没记到，等于静默丢掉")
        self.assertEqual(out["external_asserts"][0]["file"], "helper.py", out)
        # 同一次运行里「零 assert」那条闸也会响（假 TARGET 里一条 assert 都没写）。
        # 两条理由必须并列出现在 fatal 里 —— 后写的盖掉前一条，回执就会
        # 「响了但对为什么响说谎」。这一条是写这个自检时才发现的真 bug。
        self.assertIn("no tests", out.get("fatal", ""), out)

    def test_no_tests_turns_rc_9(self):
        """另一条正控的样本：模块里没有测试 ⇒ 不许安静地报绿。"""
        out = _run_fixture({
            "tests/test_fixture.py": "import unittest\n",
        })
        self.assertEqual(out["rc"], 9, out)
        self.assertIn("no tests", out.get("fatal", ""), out)
