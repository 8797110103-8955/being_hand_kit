#!/usr/bin/env python3
"""刀集执行器：一次跑完整套刀，报「红组 / 空刀 / 可区分类数」。

为什么要有这个文件（2026-11-01）：
我此前那把「13 刀矩阵」存在于一拍的工具调用 heredoc 里，仓里没有。
于是「13 刀 / 9 格 / 36 对全可分」是一个读数，不是一个能复跑的装置——
装置不在、读数还挂着，正是围炉 #34 那晚反复撞的形状。

这里把刀落成数据：KNIVES = {名字: (原文, 替换文)}。
执行时对每把刀：
  1 前置  old 必须真的在源码里（不匹配 ⇒ 这把刀根本没拨到东西）
  2 落点  子进程自报 module_sha 必须等于我写进去那份的 sha
          （「我写了」与「它读到的是那份」是两个事实）
  3 可分辨 first_red 与红组，按红组去重给「可区分类数」

空刀（rc==0，一条红都没有）不是「接住」，它有两种完全不同的含义，
报表里必须分开，否则「死代码」与「在我这套环境上恒等」长得一样：
  dead     删掉它行为永远不变（要结构论证，不能只凭一次 rc=0）
  platform 在我这台机器上恒等（posix 的 os.sep / 路径分隔符一类）
"""
import hashlib
import json
import platform
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE / "kit" / "mcp_server.py"

KNIVES = {
    # —— _code_drift ——
    "K1_changed_never": (
        "changed = sorted(k for k in now if k in was and was[k] != now[k])",
        "changed = []",
    ),
    "K2_added_missing_swapped": (
        'added = sorted(k for k in now if k not in was)\n'
        '    missing = sorted(k for k in was if k not in now)',
        'added = sorted(k for k in was if k not in now)\n'
        '    missing = sorted(k for k in now if k not in was)',
    ),
    # —— _code_snapshot ——
    "K3_pycache_kept": (
        'dirnames[:] = [x for x in dirnames if x != "__pycache__"]',
        "dirnames[:] = dirnames",
    ),
    "K4_unreadable_dropped": (
        '                except OSError:\n'
        '                    out[key] = "unreadable"',
        '                except OSError:\n'
        '                    continue',
    ),
    # —— _hot_paths（我今天刚提成独立函数的那个交集）——
    "K5_hot_is_changed": (
        "return [k for k in changed if k in loaded]",
        "return list(changed)",
    ),
    "K6_hot_is_loaded": (
        "return [k for k in changed if k in loaded]",
        "return list(loaded)",
    ),
    "K7_hot_empty": (
        "return [k for k in changed if k in loaded]",
        "return []",
    ),
    # —— _loaded_py：这台机器上恒等的一刀。posix 上 os.sep == "/"，
    #    所以 replace 是空操作 ⇒ 删掉它也 rc=0。Windows 上不是。
    "K8_loaded_relpath_sep": (
        'rel = os.path.relpath(os.path.abspath(f), root).replace(os.sep, "/")',
        "rel = os.path.relpath(os.path.abspath(f), root)",
    ),
    # —— health 里的出口：两个字段对调 ——
    "K9_health_columns_swapped": (
        '"changed": len(_ch), "loaded": len(_hot),',
        '"changed": len(_hot), "loaded": len(_ch),',
    ),
    # —— files 那格的兜底分支：_hot 为空时回落到 _ch ——
    # 所有测试样本里 _hot 都非空 ⇒ 这条 else 分支从来没被执行过。
    # 期望：空刀，但原因是「活代码 + 没有能走到它的输入」，
    # 与 K8 的「在本平台恒等」、与真死代码，是三种不同的空。
    "K10_files_fallback_collapsed": (
        '"files": _hot[:12] if _hot else _ch[:12],',
        '"files": _ch[:12],',
    ),
}


def sha8(text):
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def run_one(orig):
    r = subprocess.run([sys.executable, "tools/assert_trace.py"],
                       cwd=HERE, capture_output=True, text=True)
    line = (r.stdout or "").strip().splitlines()
    if not line:
        return {"rc": "CRASH", "stderr": (r.stderr or "")[-300:]}
    try:
        return json.loads(line[-1])
    except Exception:
        return {"rc": "UNPARSED", "raw": line[-1][:200]}


def main():
    orig = SRC.read_text()
    # 环境行必须是读出来的，不是记出来的。
    # 2026-11-01 17:3xZ 我在围炉帖的签名里写「Python 3.11」，
    # 实机是 3.10.12 —— 我签了一行自己没核过的字。那条错误在帖子发出后
    # 才被这一行同样的检查抓到，所以它从此直接印在报表头上。
    print("env python=%s os=%s impl=%s"
          % (platform.python_version(), platform.system(), platform.python_implementation()))
    print("== clean ==")
    base = run_one(orig)
    print("  rc=%s module_sha=%s first_red=%s"
          % (base.get("rc"), base.get("module_sha"),
             json.dumps(base.get("first_red", {}), ensure_ascii=False)))

    rows = []
    try:
        for name, (old, new) in KNIVES.items():
            if old not in orig:
                rows.append((name, "NO-PRECONDITION", [], None, "", ""))
                continue
            mutated = orig.replace(old, new, 1)
            SRC.write_text(mutated)
            want_sha = sha8(mutated)
            d = run_one(mutated)
            got_sha = d.get("module_sha")
            landed = (got_sha == want_sha)
            fr = d.get("first_red") or {}
            # 两级粒度都要留：只留 test 名会把「同一格红在不同行」读成同红组。
            sig = tuple(sorted(fr.items()))          # ((test, 行号), ...)
            rows.append((name, d.get("rc"), sorted(fr), want_sha, got_sha, landed, sig))
    finally:
        SRC.write_text(orig)

    print("\n== 刀 × 读数 ==")
    print("%-28s %-4s %-6s %-3s %s" % ("knife", "rc", "landed", "red", "first_red"))
    for name, rc, red, wsha, gsha, landed, _sig in rows:
        print("%-28s %-4s %-6s %-3d %s"
              % (name, str(rc), str(landed), len(red), ",".join(red) or "—"))

    empty = [r for r in rows if r[1] == 0]
    classes = {}
    classes_line = {}
    for name, rc, red, wsha, gsha, landed, sig in rows:
        if rc == "NO-PRECONDITION":
            continue
        classes_line.setdefault(sig, []).append(name)
        classes.setdefault(tuple(red), []).append(name)

    print("\n== 汇总 ==")
    same_red = [names for red, names in classes.items() if len(names) > 1]
    print("  刀数            %d" % len(KNIVES))
    print("  空刀            %d  %s" % (len(empty), [e[0] for e in empty]))
    print("  类数 test粒度   %d   行粒度 %d   （下界；两者不等说明有格红在同格不同行）"
          % (len([c for c in classes if c]), len([c for c in classes_line if c])))
    print("  同红组待分      test粒度 %d 组 %s" % (len(same_red),
          [" + ".join(g) for g in same_red]))
    same_line = [n for k, n in classes_line.items() if k and len(n) > 1]
    print("                  行粒度  %d 组 %s（这组才是真·现有格集分不开）"
          % (len(same_line), [" + ".join(g) for g in same_line]))
    for red, names in classes.items():
        if red:
            print("    类 %-40s ← %s" % (",".join(red), " + ".join(names)))
        else:
            print("    类（空）%-36s ← %s" % ("", " + ".join(names)))

    unlanded = [r[0] for r in rows if r[5] is False]
    if unlanded:
        print("  !! 未落地（我写了但被测进程没读到）: %s" % unlanded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
