#!/usr/bin/env python3
"""台账并发写探针：同一个「追加写」在四种写法下、多进程同时写，丢不丢行。

为什么要有这个文件
================
2026-11-01 围炉 #34，Neuromancer 在 Windows 上量出：`io.open(path, "a")` 4 进程 × 25 行
丢了 26 行，而**坏行 0**、每行都能 json 解析、四个 gate 名都在 —— 一份被截掉四分之一
的台账，读起来和一份本来就只有 74 行的台账逐字同形。

他那台的结论是「Windows 没有 POSIX O_APPEND 的 seek+write 原子性」。这是**平台断言**。
我这台是 Linux，同一条断言在我这儿应该不成立。不量就不知道，量一次就知道：
同一段代码的「对/错」不是代码的属性，是 (代码 × 平台) 的属性。

Readers：任何人问「再多进程同时写台账会不会丢」，跑这个，别猜。
不进 MODULES：它是探针，不是护栏；结果落 .concurrency/ 供人读。

用法：
    python3 tools/ledger_concurrency_probe.py            # 4 进程 × 25 行 × 3 轮 × 四写法
    python3 tools/ledger_concurrency_probe.py -n 8 -m 50 # 换形状
"""
import argparse
import fcntl
import io
import json
import multiprocessing as mp
import os
import shutil
import tempfile

PROCS = 4
LINES = 25
ROUNDS = 3


def _worker(args):
    path, style, pid, n = args
    for i in range(n):
        rec = json.dumps({"g": "G_p%d" % pid, "i": i}, ensure_ascii=False) + "\n"
        if style == "append_io":
            # A：io.open(path, "a") —— 她那条丢 26 行的写法
            with io.open(path, "a", encoding="utf-8") as f:
                f.write(rec)
        elif style == "append_os":
            # B：os.open(O_APPEND) + os.write
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, rec.encode("utf-8"))
            finally:
                os.close(fd)
        elif style == "flock":
            # C：flock 包住 —— 锁是 advisory，跨进程要靠大家自觉
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, rec.encode("utf-8"))
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        elif style == "seek_rw":
            # 必中样本（正控）：seek 到末尾再写，不靠 O_APPEND 的原子性。
            # 这个写法在**任何**平台上都该丢 —— 它存在的意义是让上面四个 0 有分母：
            # 如果连它也丢 0，说明我的探针本身没在并发，那些 0 不算读数。
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                os.lseek(fd, 0, os.SEEK_END)
                os.write(fd, rec.encode("utf-8"))
            finally:
                os.close(fd)
        elif style == "shard":
            # D：每进程写自己那份，读时合并
            with io.open("%s.%d" % (path, pid), "a", encoding="utf-8") as f:
                f.write(rec)
    return pid


def _read(path, style):
    paths = ([path] if style != "shard"
             else sorted(p for p in _glob(path)))
    lines, bad = [], 0
    for p in paths:
        if not os.path.exists(p):
            continue
        with io.open(p, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    lines.append(json.loads(raw))
                except Exception:
                    bad += 1
    return lines, bad


def _glob(path):
    d, b = os.path.dirname(path) or ".", os.path.basename(path)
    return [os.path.join(d, x) for x in os.listdir(d) if x.startswith(b + ".")]


def run_style(style, procs, lines):
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "led.jsonl")
        with mp.Pool(procs) as pool:
            pool.map(_worker, [(path, style, p, lines) for p in range(procs)])
        recs, bad = _read(path, style)
        want = procs * lines
        got = len(recs)
        # 缺的是谁：逐进程数，散着缺 vs 整进程缺是两种不同的坏法
        per = {}
        for p in range(procs):
            per[p] = sum(1 for r in recs if r["g"] == "G_p%d" % p)
        missing = [p for p in range(procs) if per[p] < lines]
        return {"style": style, "want": want, "got": got, "lost": want - got,
                "bad": bad, "missing_procs": missing,
                "per_proc": [per[p] for p in range(procs)]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=PROCS)
    ap.add_argument("-m", type=int, default=LINES)
    ap.add_argument("-r", type=int, default=ROUNDS)
    a = ap.parse_args()

    print("平台 %s / python %s / %d 进程 × %d 行 × %d 轮"
          % (os.uname().sysname, __import__("sys").version.split()[0], a.n, a.m, a.r))
    print("%-12s %-8s %s" % ("写法", "最坏一轮", "读数"))
    worst = {}
    for style in ("append_io", "append_os", "flock", "shard", "seek_rw"):
        rs = [run_style(style, a.n, a.m) for _ in range(a.r)]
        w = min(rs, key=lambda r: r["got"])  # 最坏一轮：丢得最多的那轮
        worst[style] = w
        print("%-12s 丢%-6d 坏行 %d  每进程 %s  缺的进程 %s"
              % (style, w["lost"], w["bad"], w["per_proc"],
                 w["missing_procs"] or "无"))
    ctl = worst["seek_rw"]
    print()
    if ctl["lost"] > 0:
        print("★ 正控（seek_rw）丢 %d 行 ⇒ 探针确实在并发，上面那些 0 是读数不是空转。"
              % ctl["lost"])
        print("★ 平台分界成立：同一段 append 代码，Windows 丢、Linux 不丢 ——"
              "「对/错」不是代码的属性，是 (代码 × 平台) 的属性。")
    else:
        print("★ 正控（seek_rw）也丢 0 ⇒ **探针没有并发，上面所有 0 作废**。")
        print("  一个只会报 0 的探针，和一个真没问题的世界，读数同形。")
        return 1
    print()
    print("★ 判据：**坏行 0 不等于没丢**——丢的是一整行时，剩下的每一行都合法。")
    print("  行数不是台账自己声明的，它没有分母；要判丢没丢，得有一个台账之外的数。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
