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
        # 测试造的世界必须自报来历：否则台账上「我造的」与「真实世界出过一次」同形。
        env["HAND_GUARD_PROVENANCE"] = "constructed:tests/test_assert_trace_selfcheck.py"
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


class LandedColumnSelfcheck(unittest.TestCase):
    """「落点」那栏（self-reported module_sha == 我写进去那份的 sha）的第一次响。

    为什么（2026-11-01 18:4x，围炉 #34 seq 4391）：我给每道闸配「响过没有」时，
    自己仓里只剩一栏是 `—`：落点 sha 不一致 ⇒ 读数作废。它恒真不是因为它稳，
    是因为**从来没有任何一次运行让「我改的那份」和「它 import 到的那份」变成两个文件**。

    真实事故形状（我今天上午真撞过同族一次）：我改 A 目录的源码，
    但 sys.path 里排在前面的 B 目录有一份同名模块 ⇒ 跑的是 B，我量的是 A。
    这一格造的就是那个形状，验的是：**回执自报的 file + sha 能不能让 driver 看见这件事。**
    """

    def test_shadowed_subject_is_visible_in_receipt(self):
        import hashlib
        import subprocess as sp
        import sys as _sys

        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / "root"      # 我改的那份所在的树
            shad = pathlib.Path(d) / "shadow"    # 实际 import 到的那份
            for base in (root, shad):
                (base / "tests").mkdir(parents=True)
                (base / "tests" / "__init__.py").write_text("")
            (root / "vendor").mkdir()
            # 我「写进去」的那份
            (root / "vendor" / "subj.py").write_text("VALUE = 'A'\n")
            # 环境里能 import 到的那份（同名、不同内容）
            (shad / "subj.py").write_text("VALUE = 'B'\n")
            (root / "tests" / "test_fixture.py").write_text(
                "import unittest\n"
                "class TestFixture(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertEqual(1, 1)\n"
            )
            env = dict(os.environ)
            env["HAND_GUARD_PROVENANCE"] = "constructed:tests/test_assert_trace_selfcheck.py"
            env.update(PYTHONPATH=str(shad), ASSERT_TRACE_ROOT=str(root),
                       ASSERT_TRACE_TARGET=str(root / "tests" / "test_fixture.py"),
                       ASSERT_TRACE_MODULE="tests.test_fixture",
                       ASSERT_TRACE_SUBJECT="subj")
            proc = sp.run([_sys.executable, str(TOOL)], cwd=str(root), env=env,
                          capture_output=True, text=True, timeout=120)
            lines = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
            self.assertTrue(lines, proc.stdout[-800:] + proc.stderr[-800:])
            out = json.loads(lines[-1])

            want = hashlib.sha256((root / "vendor" / "subj.py").read_bytes()).hexdigest()[:8]
            got_file = pathlib.Path(out["module_file"] or "")
            got = out["module_sha"]

            # 1 它自报了落点文件——不是「一个 sha」了事，得指得出来源
            self.assertEqual(got_file.name, "subj.py", out)
            # 2 它读到的是影子那份，不是我写的那份
            self.assertEqual(str(got_file.resolve()).startswith(str(shad.resolve())), True, out)
            self.assertNotEqual(got, want, "落点栏没响：它读的就是我写的那份")
            # 3 于是 driver 那一句 `got_sha == want_sha` 在这里为 False ⇒ 读数该作废
            self.assertFalse(got == want)
            self.assertEqual(proc.returncode, 0, "落点不一致不是装置坏了，读数作废另有其栏")
