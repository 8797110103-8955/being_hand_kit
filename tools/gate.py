#!/usr/bin/env python3
"""驱动侧对账：我叫了它一次，台账里就必须多一行。

为什么有这个东西（2026-11-01T21:2xZ）
--------------------------------------
台账是闸**自己**写自己的——闸调 `guard_note()` 记「我跑过、我响过」。
于是有一道闸从未被调用时，表里连「没跑过」都不出现：**「没跑过」与
「忘了记账」同形**。这正是 Neuromancer 拒绝给 dead_gate_scan 装台账的理由
（「记在它自己写的文件里＝同一条证据的两个副本」）——他在自己的装置上看见了，
我在自己的装置上没看见。

判据写成一句可操作的：**写那一行的进程，不能是被审物自己的运行。谁写 > 写哪儿。**
这一层就是那个「另一个写者」：驱动侧发出 run_id，跑完回读台账，数这个 run_id 的行数。

用法
----
    python3 tools/gate.py tools/roster_extract.py /tmp/raw.txt
    python3 tools/gate.py --provenance constructed tools/zero_stamp.py f.py

出口
----
  rc = 工具自己的 rc            —— 对账通过（这次调用恰好留了一行）
  rc = 9  LEDGER_LOST          —— 驱动侧数了 1 次调用，台账 0 行：这一发没进账
  rc = 4  LEDGER_DOUBLED       —— 一次进程留了 N>1 行：同一个动作记了两次
  rc = 3  GATE_CRASHED         —— 工具没跑起来（找不到/不可执行）

★ 这一层也有它抓不到的东西，明写在这里，免得被当成全序：
  - 它只对「经它调用的那一次」对账。我用别的方式直接跑工具，它一无所知。
  - 它抓不到「台账写到了别处」——那需要外部分母（文件是否存在）。
  - 一行恰好丢了尾字节会读成坏行，那是读侧对账的事，不是这一层。
"""
import json
import os
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEDGER = os.path.join(HERE, "..", ".guard_ledger.jsonl")


def _ledger_path(env):
    return env.get("HAND_GUARD_LEDGER") or DEFAULT_LEDGER


def _rows_with(run_id, path):
    n = 0
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("run_id") == run_id:
                n += 1
    return n


def main(argv):
    args = list(argv[1:])
    provenance = None
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--provenance":
            provenance = args.pop(0)
        else:
            sys.stderr.write("unknown flag %s\n" % flag)
            return 3
    if not args:
        sys.stderr.write("usage: gate.py [--provenance P] <tool.py> [args...]\n")
        return 3

    tool, rest = args[0], args[1:]
    if not os.path.exists(tool):
        sys.stderr.write("GATE_CRASHED: 没有这个工具 %s\n" % tool)
        return 3

    run_id = uuid.uuid4().hex[:12]
    env = dict(os.environ)
    env["HAND_GUARD_RUN_ID"] = run_id
    # 样本身份＝这次调用的 argv（截短）。闸自己不许编这个——它不知道谁叫它。
    env["HAND_GUARD_SAMPLE"] = (" ".join([os.path.basename(tool)] + rest))[:80]
    if provenance:
        env["HAND_GUARD_PROVENANCE"] = provenance
    path = _ledger_path(env)

    proc = subprocess.run([sys.executable, tool] + rest, env=env,
                          capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    rows = _rows_with(run_id, path)
    # 驱动侧的数是我自己数的，不是读台账读出来的——两个数在这里相遇。
    if rows == 0:
        sys.stderr.write(
            "!! LEDGER_LOST: 驱动侧数了 1 次调用，台账 0 行"
            "（run_id=%s，%s，子进程 rc=%d）\n"
            "   这一发没进账。带子进程 rc 是因为两种情形在账上同形、要人分得开：\n"
            "     rc=0  ⇒ 它自己说没事，却一行没留 —— 它根本没接台账\n"
            "     非 0  ⇒ 它死在记账之前（崩在哪一层，看它自己的 stderr）\n"
            % (run_id, path, proc.returncode))
        return 9
    if rows > 1:
        sys.stderr.write(
            "!! LEDGER_DOUBLED: 一次进程留了 %d 行（run_id=%s）——同一个动作记了两次\n"
            % (rows, run_id))
        return 4
    sys.stderr.write("对账通过：调用 1 次 / 台账 1 行（run_id=%s）\n" % run_id)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
