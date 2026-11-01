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


if __name__ == "__main__":
    unittest.main(verbosity=2)
