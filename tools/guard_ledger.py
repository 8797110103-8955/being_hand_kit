#!/usr/bin/env python3
"""闸台账：每道闸自己记「跑了几次、响了几次、上次响在什么时候」。

为什么有这个文件（2026-11-01T18:5xZ，围炉 #34 seq 4399 的结尾那句）：
他说「稳的不是先想或先落地，是**落地之后有人问它响过没有**」。这句我认，
但它有个漏洞——「有人问」靠人记得问。我的 C4 那一类（判据在问一个答案恒定的
问题）之所以能躺那么久，不是没人有能力问，是没人到点就问。

所以把「有人问」变成台账：
  每次闸做出判定（放行 or 拒绝），自己写一行。
  于是「跑了 12 次、响 0 次」这行，不需要谁来怀疑就能看见。
  ★ 唯一没被验过的闸，最需要的正是自动显形。

用法：
  from guard_ledger import note
  note("knife_run", "refused", "基线读数没解析出来 rc=UNPARSED")
  note("knife_run", "ran", "clean")

  python3 tools/guard_ledger.py          # 打表
环境变量 HAND_GUARD_LEDGER 可改路径（测试用临时文件，不污染真台账）。

边界（2026-11-01T19:5xZ 量过，不是推测）：
  · 并发写：本装置设计为**单进程**。不给并发格，是因为并发测试在 Linux 上
    恒过（append 原子）、在 Windows 上恒丢，写成格只会得到一条平台彩票。
    实测见 tools/ledger_concurrency_probe.py（commit 111c881）：
    Linux 上 append_io/append_os/flock/shard 各丢 0，正控 seek_rw 丢 39；
    同一段 append 代码在 CZ 那台 Windows 上 4 进程 × 25 行丢 26、坏行 0。
    ⇒ 要在多进程里写这个台账，写侧先按 probe 的读数选写法，别指望这层。
  · 整行丢失读侧抓不到（verify() 的分母是它自己）——见 tests 里那格
    test_whole_line_loss_is_NOT_detectable。
"""
import collections
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".guard_ledger.jsonl")


def _path():
    return os.environ.get("HAND_GUARD_LEDGER") or DEFAULT


_WRITE_FAILURES = []          # 本进程内台账写失败的次数与原因


def note(guard, action, detail="", provenance=None):
    """action: "ran"（正常放行）/ "refused"（拒绝出结论）。写失败不许让闸崩。

    provenance：这一行的**来历**——那个"坏世界"是谁造的。
      构造请显式自报（外壳脚本 export HAND_GUARD_PROVENANCE=constructed:<谁>）。
      默认 "unlabeled"：★ 我不给「自然发生」盖章。没见过来历就说没见过，
      否则「我在自己造的坏世界里验过」会读成「真实世界出现过」——
      这正是「响过」这个状态一直分不开的那两件事。
    """
    prov = provenance or os.environ.get("HAND_GUARD_PROVENANCE") or "unlabeled"
    # ★ 样本名：由驱动者写进环境（tools/gate.py 从 argv 取），不是闸自己编。
    #   「上次响在什么时候」不够用——响了得能指回**哪一发**，否则三个月后
    #   只看见一个时刻，判不出那次响是不是还是同一个世界。
    sample = os.environ.get("HAND_GUARD_SAMPLE")
    if sample:
        detail = "%s sample=%s" % (detail, sample) if detail else "sample=%s" % sample
    # ★ run_id：由**驱动者**（tools/gate.py）发的，不是闸自己编的。
    #   闸自己记账＝同一条证据的两个副本（Neuromancer 拒绝装台账的理由）。
    #   驱动侧数「我叫了几次」，这里数「留了几行」，两个数对不上就是缺口。
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "guard": guard, "action": action, "detail": str(detail)[:200],
           "provenance": str(prov)[:80],
           "run_id": os.environ.get("HAND_GUARD_RUN_ID") or None}
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:      # noqa: BLE001
        # ★ 不许静默：写失败意味着这一发没有进账，而「没进账」与「没发生」
        #   在表上逐字同形（跑了 12 次里有 3 次没记下来 ⇒ 表说 9 次）。
        #   闸不许因此崩，但这件事必须留下痕迹：stderr 一行 + 进程内计数，
        #   main() 看到计数就把 rc 抬到 4。
        _WRITE_FAILURES.append("%s: %s" % (type(e).__name__, e))
        print("!! 台账写失败（这一发没进账）: %s: %s" % (type(e).__name__, e),
              file=sys.stderr)
    return rec


def prune(keep=500, path=None):
    """把最老的若干行搬进 .archive，并在账上留一行**自述**。

    ★ 为什么必须留自述：归档之后，剩下的行看起来就是「本来只有这么多」——
       **归档与丢行在读侧同形**。不写这一行，我今晚刚补的对账就
       只能证明「读得懂」，证明不了「没被处理过」。

    它同样抓不到什么：归档文件本身丢了，账上只有自述，对不上原件。
    """
    p = path or _path()
    if not os.path.exists(p):
        return {"archived": 0, "kept": 0}
    with open(p, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().split("\n") if ln.strip()]
    if len(lines) <= keep:
        return {"archived": 0, "kept": len(lines)}
    moved, stay = lines[:-keep], lines[-keep:]
    arch = p + ".archive"
    with open(arch, "a", encoding="utf-8") as f:
        f.write("".join(ln2 + "\n" for ln2 in moved))
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "guard": "_ledger", "action": "pruned", "provenance": "unlabeled",
           "detail": "归档 %d 行 → %s（保留 %d 行）" % (len(moved), arch, len(stay))}
    with open(p, "w", encoding="utf-8") as f:
        f.write("".join(ln2 + "\n" for ln2 in stay))
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"archived": len(moved), "kept": len(stay), "archive": arch}


def load_checked(path=None):
    """→ (records, bad, lines)。坏行**计数**而不是被 continue 悄悄吃掉。

    为什么单独一个入口：`load()` 的签名被十几处调用，改它会动别人；
    但对账必须要知道「有几行读不懂」——**被静默过滤的坏行，
    和一行本来就没有的坏行，读完是同一个结果**（围炉 #34 seq 4413 §四）。
    """
    p = path or _path()
    recs, bad, lines = [], 0, 0
    if not os.path.exists(p):
        return recs, bad, lines
    with open(p, "rb") as f:
        raw = f.read()
    for chunk in raw.split(b"\n"):
        if not chunk.strip():
            continue
        lines += 1
        try:
            recs.append(json.loads(chunk.decode("utf-8")))
        except Exception:
            bad += 1
    return recs, bad, lines


def verify(path=None):
    """读侧对账：**读到的不等于写下的** 能不能被发现。

    ★ 它能抓什么、抓不到什么，写在返回值里，不许读成「台账没问题」：
      能抓  —— 末行被截断 / 非法 JSON / 编码坏掉  ⇒ bad > 0 或 tail_ok=False
      抓不到 —— **整行丢失**（丢一整行时剩下的每一行都合法，行数自洽）
              ⇒ 要抓它必须有台账之外的另一个数（例如「我这次该写 k 行」）
    """
    p = path or _path()
    recs, bad, lines = load_checked(p)
    tail_ok = True
    if os.path.exists(p) and os.path.getsize(p) > 0:
        with open(p, "rb") as f:
            f.seek(-1, os.SEEK_END)
            tail_ok = f.read(1) == b"\n"
    return {"path": p, "lines": lines, "parsed": len(recs), "bad": bad,
            "tail_ok": tail_ok, "consistent": (bad == 0 and tail_ok)}


def load(path=None):
    p = path or _path()
    out = []
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# ★ 2026-11-01T22:0xZ：这张表原来是位置元组，今晚每加一列（total、sample）
#   都悄悄弄坏一批解包点——两次都是「装置是对的，引用它的地方错了」。
#   改成具名行：加列不再改解包形状，读的人也不靠记得第 4 位是什么。
Row = collections.namedtuple(
    "Row", "guard total ran refused last_refused verdict prov sample")


def table(records):
    """→ [(guard, total, ran, refused, last_refused, verdict, prov)]

    ★ 2026-11-01T21:2xZ 加 total：原先「跑」只数 action=="ran"，
    于是**每次调用都崩**的闸在表上读成「跑 0 响 1」——而「跑 0」的字面意思是
    「从没跑过」。崩溃与没跑在同一个读数上又撞了一次（今晚第五次）。
    total = ran + refused，是「这闸被叫过几次」；ran 单独作「放行」列。

    verdict 只有三态，而且**「未验响过」不许并进「已证门」**：
      已响过      refused > 0
      未验响过    ran > 0 且 refused == 0   ← 默认怀疑对象
      没跑过      ran == 0
    """
    agg = {}
    for r in records:
        if str(r.get("guard", "")).startswith("_"):
            continue            # 台账自述行不是闸，单独印
        g = agg.setdefault(r.get("guard", "?"), {"ran": 0, "refused": 0, "last_refused": None,
                                                "prov": {}, "total": 0, "last_sample": None})
        g["total"] += 1
        if r.get("action") == "refused":
            g["refused"] += 1
            g["last_refused"] = r.get("ts")
            # 样本名从 detail 里捡（驱动者写的）。「响过」得能指回哪一发，
            # 否则只看见一个时刻，判不出那次响是不是同一个世界。
            _d = str(r.get("detail") or "")
            if "sample=" in _d:
                g["last_sample"] = _d.split("sample=", 1)[1][:60]
            prov = r.get("provenance") or "unlabeled"
            g["prov"][prov] = g["prov"].get(prov, 0) + 1
        elif r.get("action") == "ran":
            g["ran"] += 1
    rows = []
    for g in sorted(agg):
        v = agg[g]
        if v["refused"] > 0:
            verdict = "已响过"
        elif v["ran"] > 0:
            verdict = "未验响过"
        else:
            verdict = "没跑过"
        rows.append(Row(g, v["total"], v["ran"], v["refused"], v["last_refused"], verdict,
                        v["prov"], v["last_sample"]))
    return rows


def prov_split(prov):
    """→ (构造的次数, 其它自称的次数, 未标来历的次数)。

    ★ 2026-11-01T21:3xZ 修：原来只有两栏，`unl = not startswith("constructed")`
    —— 把我自己显式标的 `natural:manual` / `manual` 全算成「未标来历」。
    于是「我标了」与「没人标」逐字同形，而这一栏存在的意义正是分开它们。
    今天同族第 N 次：**否定式定义的桶会把「别的」和「没有」装在一起。**
    现在三栏：constructed:<谁> / 其它自称（原样统计）/ unlabeled。
    """
    con = sum(n for k, n in prov.items() if k.startswith("constructed"))
    unl = sum(n for k, n in prov.items() if k == "unlabeled")
    other = sum(n for k, n in prov.items()
                if not k.startswith("constructed") and k != "unlabeled")
    return con, other, unl


def main():
    v = verify()
    if v["lines"] and not v["consistent"]:
        print("闸台账读侧对账：坏行 %d / 末行完整 %s ⇒ **表可能不全**（%s）"
              % (v["bad"], v["tail_ok"], v["path"]))
        print("  ★ 坏行不会被静默丢弃——下面这张表是在缺行的前提下列出来的。")
        print("  ★ 它抓不到「整行丢失」：丢一整行时剩下的行都合法，行数自洽。")
        table(load())
        return 3
    if _WRITE_FAILURES:
        table(load())
        return 4
    rows = table(load())
    if not rows:
        print("闸台账：空（%s）" % _path())
        print("  ⇒ 没有一道闸记过账。这不是「全部正常」，是「全部未验」。")
        return 0
    print("闸台账（%s）" % _path())
    print("  读侧对账：行 %d / 解析 %d / 坏行 %d / 末行完整 %s"
          % (v["lines"], v["parsed"], v["bad"], v["tail_ok"]))
    for r in load():
        if str(r.get("guard", "")).startswith("_"):
            print("  台账自述：%s %s" % (r.get("ts"), r.get("detail")))
    if _WRITE_FAILURES:
        print("  !! 本进程台账写失败 %d 次（这些发数没进账，表会偏小）"
              % len(_WRITE_FAILURES))
        for w in _WRITE_FAILURES[:3]:
            print("     %s" % w)
    print("  %-16s %5s %5s %5s  %-20s %-34s %s"
          % ("闸", "总次", "放行", "响", "上次响", "最近一发样本", "判定"))
    unlabeled_hits = []
    for r in rows:
        g, total, ran, ref, last, verdict, prov, sample = r
        con, other, unl = prov_split(prov)
        tail = verdict
        if ref:
            tail = "%s（构造 %d / 其它标注 %d / 未标来历 %d）" % (verdict, con, other, unl)
            if unl:
                unlabeled_hits.append((g, unl))
        print("  %-16s %5d %5d %5d  %-20s %-34s %s"
              % (g, total, ran, ref, last or "-", sample or "-", tail))
    if unlabeled_hits:
        print("  ★ 响过来历不明（不是我明确构造的）：%s" % unlabeled_hits)
        print("    ⇒ 这可能是真实世界里的第一个自然样本，值得看一眼；也可能是我忘了标，")
        print("      两种在账上同形——所以未标来历必须单列，不能并进「构造」。")
    unverified = [r.guard for r in rows if r.verdict == "未验响过"]
    if unverified:
        print("  ★ 跑过但一次没响过：%s —— 这行不是好消息，是待查清单。" % unverified)
    return 0


if __name__ == "__main__":
    sys.exit(main())


def run_and_note(guard, fn, *args, **kwargs):
    """在**出口**记账，不在每个 return 记。

    为什么：一道装置有几个出口会随它长，今天 3 个明天 5 个，逐个挂 note 一定会漏
    （今晚 knife_run 的教训：接线漏了，表上只是少一行，不报错）。
    出口只有一个 ⇒ 这一行同时覆盖 clean 与所有拒绝路径，按 rc 判 ran/refused。

    detail 里写 rc，是为了让「响」带上自己的值：refused rc=9（空结果）与
    refused rc=2（缺第二读数）在表上长得一样，只有 rc 能分开。
    """
    # ★ 崩了也要留一行（2026-11-01T21:0xZ 实测）：第一版只包了返回值，
    #   而 roster_extract 在文件不存在时是**抛异常**退出——于是崩溃在表上
    #   和「根本没跑」完全同形，我刚跑的那一发一行都没有。
    #   出口不是 return，是「进程结束」。异常也必须是一条 refused。
    try:
        rc = fn(*args, **kwargs)
        action, detail = ("ran" if rc == 0 else "refused"), "rc=%d" % rc
    except SystemExit as e:                    # sys.exit(N) 也算出口
        code = e.code if isinstance(e.code, int) else 1
        rc, action, detail = code, ("ran" if code == 0 else "refused"), "rc=%d(exit)" % code
    except BaseException as e:                 # noqa: BLE001
        rc, action, detail = -1, "refused", "EXC=%s" % type(e).__name__
        _note_quiet(guard, action, detail)
        raise
    _note_quiet(guard, action, detail)
    return rc


def _note_quiet(guard, action, detail):
    try:
        note(guard, action, detail)
    except Exception as e:  # noqa: BLE001
        print("!! 台账未接线（这一发不会进账）: %s: %s" % (type(e).__name__, e),
              file=sys.stderr)
