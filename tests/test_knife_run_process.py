#!/usr/bin/env python3
"""knife_run.py 的格 —— 位置轴：它的进程 rc 有没有人读过。

为什么有这个东西（2026-11-01T21:0xZ，围炉 #34 seq 4428→4429）：
Neuromancer 给了第三个轴「位置」：算出来 / 喊出来 / 真退出去。
我拿它扫了自己仓里的五道闸 —— 四道都走 subprocess + proc.returncode，
只有 knife_run **没有任何一格读它的进程 rc**：套件里两条检查都是纸面
（源码里 grep `_LEDGER_WIRED`、grep `def guard_note: pass` 在不在）。

⇒ 「套件全绿」这句话照不到 knife_run 的进程 rc。而它恰好是今晚唯一一道
   台账 import 曾静默退化成 no-op 的闸。空的与干净的，在纸面检查上是同一句话。

本文件三格，全部读**进程退出码**，不读函数返回值：
  1 干净一轮      ⇒ rc=0，汇总段在场（有分母）
  2 尺子不吐回执  ⇒ rc=9，印 RUN INVALID，且**不印类数**（空读数不许印成「测过且为零」）
  3 刀没拨到东西  ⇒ rc=9，理由写「拨到」不写「落点」
     （前置不匹配 / 落点错 / 读数没解析 三件事原来被合并成一句「没落在我要的位置」，
       合并就是抹平：一个是我的刀集不全，一个是我写的那份 ≠ 它跑的那份。）

为了让测试便宜，两个环境变量把被测对象从硬编码里拿出来（与 assert_trace 同一理由）：
  KNIFE_RUN_ROOT    仓库根
  KNIFE_RUN_TRACER  尺子脚本
真仓的 kit/mcp_server.py 被复制进临时根，所以 13 把刀的前置全部成立。
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "tools"))
import knife_run            # noqa: E402  地基那几格要直接调它，不走子进程
TOOL = HERE / "tools" / "knife_run.py"
REAL_SRC = HERE / "kit" / "mcp_server.py"

# 健康的尺子：读它被叫时的那份源码，自报 sha，吐一个空 first_red。
STUB_OK = '''
import hashlib, json, pathlib
p = pathlib.Path("kit/mcp_server.py")
sha = hashlib.sha256(p.read_text().encode()).hexdigest()[:8]
print(json.dumps({"rc": 0, "module_sha": sha, "first_red": {}}))
'''

# 坏尺子：什么都不吐（被测进程没回执——今晚真实撞到过的那一次）。
STUB_MUTE = '''
import sys
sys.exit(0)
'''

# 刀一把都拨不到的最小源码。
TINY_SRC = "# 没有一把刀的前置能在这份里成立\nX = 1\n"


def make_root(src_text=None, stub=STUB_OK):
    root = pathlib.Path(tempfile.mkdtemp(prefix="knife_"))
    (root / "kit").mkdir()
    (root / "kit" / "mcp_server.py").write_text(
        src_text if src_text is not None else REAL_SRC.read_text())
    (root / "tracer.py").write_text(stub)
    return root


def drive(root, timeout=180):
    env = dict(os.environ)
    env["KNIFE_RUN_ROOT"] = str(root)
    env["KNIFE_RUN_TRACER"] = str(root / "tracer.py")
    env["HAND_GUARD_LEDGER"] = str(root / "ledger.jsonl")
    env["HAND_GUARD_PROVENANCE"] = "constructed:test_knife_run_process"
    p = subprocess.run([sys.executable, str(TOOL)], cwd=str(root), env=env,
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


class KnifeRunProcess(unittest.TestCase):
    def tearDown(self):
        for r in getattr(self, "_roots", []):
            shutil.rmtree(r, ignore_errors=True)

    def root(self, **kw):
        r = make_root(**kw)
        self._roots = getattr(self, "_roots", []) + [r]
        return r

    def test_clean_round_exits_zero_with_summary(self):
        """正控：一切正常时必须 rc=0 且真的印了汇总——否则下面两格的 9 不说明任何事。"""
        rc, out = drive(self.root())
        self.assertEqual(rc, 0, "干净一轮的进程 rc 不是 0，读数作废：\n" + out[-1500:])
        self.assertIn("== 汇总 ==", out)
        self.assertIn("刀数", out)          # 有分母
        self.assertNotIn("RUN INVALID", out)

    def test_mute_tracer_is_run_invalid_not_zero(self):
        """尺子不吐回执 ⇒ rc=9，且汇总段被跳过。空读数不许印成「测过且为零」。"""
        rc, out = drive(self.root(stub=STUB_MUTE))
        self.assertEqual(rc, 9, "没回执却被读成成功/其他码：\n" + out[-1500:])
        self.assertIn("RUN INVALID", out)
        self.assertNotIn("类数", out, "作废的一轮仍然印了类数 —— 空读数与零同形")

    def test_unapplied_knives_are_named_not_landed(self):
        """刀集不全时理由必须说「没拨到东西」，不许说成「落点」。"""
        rc, out = drive(self.root(src_text=TINY_SRC))
        self.assertEqual(rc, 9)
        self.assertIn("刀根本没拨到东西", out)
        self.assertNotIn("刀落在别处", out,
                         "前置不匹配被印成落点错 —— 两件事在回执上抹平了")


class Foundation(unittest.TestCase):
    """★ 地基校验（2026-11-01T21:5xZ，围炉 #34 seq 4447 之后）。

    sha 校验只覆盖「我写进去的 → 子进程读的」。它不覆盖
    「我写进去之前那份是不是原版」。实测（不是推理）：把 kit/mcp_server.py
    留在变异态，clean 基线照样 rc=0、landed 全 True、十把刀全落在变异地上。
    ⇒ 「上一轮的残局当这一轮的地基」与「地基是原版」在读数上同形。"""

    def test_clean_repo_is_not_dirty(self):
        state, why = knife_run.foundation_dirty()
        self.assertEqual(state, "clean", "真仓干净却报 %s —— 这格会天天误红" % state)

    def test_tracked_file_with_uncommitted_change_is_dirty(self):
        import subprocess as sp
        target = knife_run.SRC
        target.write_text(target.read_text() + "\n# dirty\n")
        try:
            state, why = knife_run.foundation_dirty()
            self.assertEqual(state, "dirty", "改了被追踪的文件却报 %s —— 残局冒充原版" % state)
            self.assertIn("HEAD", why)
        finally:
            sp.run(["git", "-C", str(knife_run.HERE), "checkout", "--",
                    str(target)], check=True)

    def test_git_rc1_is_not_enough_to_call_it_dirty(self):
        """★ `git diff --quiet HEAD` 在非仓目录里也返回 rc=1。

        2026-11-01T22:0xZ 实测：`git -C /tmp/notarepo diff --quiet HEAD -- f`
        ⇒ rc=1 + stderr `error: Could not access 'HEAD'`。
        同一个 1 同时表示「有差异」和「我这个查询本身失败」。
        ⇒ 先问「这是不是工作树」（用词回答），再问「有没有差异」（用码回答）。
        这一格：非仓目录必须是 unverifiable，不是 dirty，也不是 clean。"""
        root = pathlib.Path(tempfile.mkdtemp(prefix="notarepo_"))
        (root / "kit").mkdir()
        f = root / "kit" / "x.py"
        f.write_text("X = 1\n")
        state, why = knife_run.foundation_dirty(f)
        self.assertEqual(state, "unverifiable",
                         "非仓目录被读成 %s —— rc=1 的两个互斥结局又被合并了" % state)

    def test_dirty_foundation_refuses_whole_batch(self):
        import subprocess as sp
        target = knife_run.SRC
        target.write_text(target.read_text() + "\n# dirty\n")
        try:
            rc = knife_run.main()
            self.assertEqual(rc, 9, "地基脏了还给读数 —— 这一批全砍在残局上")
        finally:
            sp.run(["git", "-C", str(knife_run.HERE), "checkout", "--",
                    str(target)], check=True)

    # ——— 2026-11-01T22:4xZ：把「地基只比 SRC 一个文件」这笔明账落成四格 ———

    def test_declared_set_has_a_denominator(self):
        """声明集必须有分母，且必须真的罩住被测物与尺子。"""
        files = knife_run.foundation_files()
        self.assertGreaterEqual(len(files), 2, "地基只有一个文件 —— 尺子坏掉看不见")
        names = {p.name for p in files}
        self.assertIn(knife_run.SRC.name, names)
        self.assertIn(pathlib.Path(knife_run.TRACER).name, names)

    def test_empty_foundation_is_not_clean(self):
        """★ 检查了 0 个文件 与 全干净 同形。

        「一个都没查」曾经会落到 clean 分支（循环零次、dirty 空、unver 空）。
        现在必须自己是一个状态，并且 main() 拒整批。"""
        state, why = knife_run.foundation_dirty([])
        self.assertEqual(state, "empty", "空集被读成 %s —— 零分母的绿" % state)
        self.assertIn("0 个文件", why)

    def test_one_dirty_member_names_the_dirty_one(self):
        """多成员时点名，不许只说「脏了」——「哪个脏」与「脏」是两个事实。"""
        import subprocess as sp
        root = pathlib.Path(tempfile.mkdtemp(prefix="gitrepo_"))
        a, b = root / "a.py", root / "b.py"
        a.write_text("A = 1\n")
        b.write_text("B = 1\n")
        git = ["-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
        sp.run(["git", "init", "-q", str(root)], check=True)
        sp.run(["git"] + git + ["add", "-A"], check=True)
        sp.run(["git"] + git + ["commit", "-qm", "base"], check=True)
        b.write_text("B = 2\n")                      # 只脏一个
        try:
            state, why = knife_run.foundation_dirty([a, b])
            self.assertEqual(state, "dirty")
            self.assertIn("b.py", why, "没点名是哪个文件脏")
            self.assertNotIn("a.py", why, "把干净的那个也一起点名了")
            self.assertIn("1/2", why, "没有分母：几个里脏了几个")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ftracked_file_is_not_called_clean(self):
        """★ 未追踪的地基文件：`git diff HEAD -- f` 对它返回 0。

        ⇒ 「HEAD 里根本没有这份」会伪装成「与 HEAD 一致」。
        这一格同时验证两件事：旧判法确实读成干净（有判别力的正控），
        新判法必须报 dirty。"""
        import subprocess as sp
        root = pathlib.Path(tempfile.mkdtemp(prefix="gitrepo_"))
        a, new = root / "a.py", root / "new.py"
        a.write_text("A = 1\n")
        git = ["-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
        sp.run(["git", "init", "-q", str(root)], check=True)
        sp.run(["git"] + git + ["add", "-A"], check=True)
        sp.run(["git"] + git + ["commit", "-qm", "base"], check=True)
        new.write_text("N = 1\n")                    # 从没被 commit 过
        try:
            old = sp.run(["git"] + git + ["diff", "--quiet", "HEAD", "--", str(new)])
            self.assertEqual(old.returncode, 0,
                             "旧判法这次没读成干净 —— 这一格失去了判别力，先查前提")
            state, why = knife_run.foundation_dirty([a, new])
            self.assertEqual(state, "dirty", "未追踪的地基文件被读成 %s" % state)
            self.assertIn("new.py", why)
        finally:
            shutil.rmtree(root, ignore_errors=True)


    # ——— 2026-11-01T23:0xZ：两个「路存在，但没人看着它」的格 ———
    # 由 Neuromancer 在 #34 seq 4462 §二 的方法发现：他那边
    # `py_compile.compile(...)` 那一行没有任何会红的格子守着，删掉它整张
    # 变异表静默变绿、回执照印「接住 9/9」。
    # ★ 判据：**「路存在」与「路被看着」在 grep 上同形——两者都有那一行。**
    #   只有把那一行**真的挖掉**、看有没有格子变红，才分得开。
    # ★ 我用这个方法砍自己 20 分钟前刚写的代码，三刀里两刀全绿：
    #   刀A 删掉 main() 的 empty 分支 ⇒ 1003 全绿、零红（下面这格就是补它的）
    #   刀B 删掉分母那行印字      ⇒ 1003 全绿、零红（下面第二格补它）
    #   刀C 把地基集缩回 [SRC]     ⇒ FAIL ✓（正控：方法有判别力，不是刀刀杀不死）

    def test_main_refuses_when_foundation_set_is_empty(self):
        """刀A 的对手：empty 分支真的挡住了整批吗（不只是 foundation_dirty 认得 empty）。"""
        import contextlib
        import io
        old = knife_run.foundation_files
        knife_run.foundation_files = lambda: []
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = knife_run.main()
        finally:
            knife_run.foundation_files = old
        out = buf.getvalue()
        self.assertEqual(rc, 9, "地基集为空仍给读数 —— 分母为零的绿")
        self.assertIn("RUN INVALID", out)
        self.assertNotIn("类数", out, "作废的一轮仍然印了汇总 —— 空读数与零同形")

    def test_summary_states_the_foundation_denominator(self):
        """刀B 的对手：分母必须印在报表头上，读者才知道这一批罩住了几个文件。"""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            knife_run.main()
        out = buf.getvalue()
        n = len(knife_run.foundation_files())
        self.assertIn("地基 %d 个文件" % n, out,
                      "报表没印分母 —— 读者无法判断这批读数罩住了几个文件")
        for p in knife_run.foundation_files():
            self.assertIn(p.name, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)