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
"""
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".guard_ledger.jsonl")


def _path():
    return os.environ.get("HAND_GUARD_LEDGER") or DEFAULT


def note(guard, action, detail="", provenance=None):
    """action: "ran"（正常放行）/ "refused"（拒绝出结论）。写失败不许让闸崩。

    provenance：这一行的**来历**——那个"坏世界"是谁造的。
      构造请显式自报（外壳脚本 export HAND_GUARD_PROVENANCE=constructed:<谁>）。
      默认 "unlabeled"：★ 我不给「自然发生」盖章。没见过来历就说没见过，
      否则「我在自己造的坏世界里验过」会读成「真实世界出现过」——
      这正是「响过」这个状态一直分不开的那两件事。
    """
    prov = provenance or os.environ.get("HAND_GUARD_PROVENANCE") or "unlabeled"
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "guard": guard, "action": action, "detail": str(detail)[:200],
           "provenance": str(prov)[:80]}
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return rec


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


def table(records):
    """→ [(guard, ran, refused, last_refused, verdict)]

    verdict 只有三态，而且**「未验响过」不许并进「已证门」**：
      已响过      refused > 0
      未验响过    ran > 0 且 refused == 0   ← 默认怀疑对象
      没跑过      ran == 0
    """
    agg = {}
    for r in records:
        g = agg.setdefault(r.get("guard", "?"), {"ran": 0, "refused": 0, "last_refused": None,
                                                "prov": {}})
        if r.get("action") == "refused":
            g["refused"] += 1
            g["last_refused"] = r.get("ts")
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
        rows.append((g, v["ran"], v["refused"], v["last_refused"], verdict, v["prov"]))
    return rows


def prov_split(prov):
    """→ (构造的次数, 未标来历的次数)。已响过必须按来历拆开印：
    同一栏里「我造的坏世界」与「不知道谁造的」数值相同，读起来是同一件事。"""
    con = sum(n for k, n in prov.items() if k.startswith("constructed"))
    unl = sum(n for k, n in prov.items() if not k.startswith("constructed"))
    return con, unl


def main():
    v = verify()
    if v["lines"] and not v["consistent"]:
        print("闸台账读侧对账：坏行 %d / 末行完整 %s ⇒ **表可能不全**（%s）"
              % (v["bad"], v["tail_ok"], v["path"]))
        print("  ★ 坏行不会被静默丢弃——下面这张表是在缺行的前提下列出来的。")
        print("  ★ 它抓不到「整行丢失」：丢一整行时剩下的行都合法，行数自洽。")
        table(load())
        return 3
    rows = table(load())
    if not rows:
        print("闸台账：空（%s）" % _path())
        print("  ⇒ 没有一道闸记过账。这不是「全部正常」，是「全部未验」。")
        return 0
    print("闸台账（%s）" % _path())
    print("  读侧对账：行 %d / 解析 %d / 坏行 %d / 末行完整 %s"
          % (v["lines"], v["parsed"], v["bad"], v["tail_ok"]))
    print("  %-16s %5s %5s  %-20s %s" % ("闸", "跑", "响不过", "上次响", "判定"))
    unlabeled_hits = []
    for g, ran, ref, last, verdict, prov in rows:
        con, unl = prov_split(prov)
        tail = verdict
        if ref:
            tail = "%s（构造 %d / 未标来历 %d）" % (verdict, con, unl)
            if unl:
                unlabeled_hits.append((g, unl))
        print("  %-16s %5d %5d  %-20s %s" % (g, ran, ref, last or "-", tail))
    if unlabeled_hits:
        print("  ★ 响过来历不明（不是我明确构造的）：%s" % unlabeled_hits)
        print("    ⇒ 这可能是真实世界里的第一个自然样本，值得看一眼；也可能是我忘了标，")
        print("      两种在账上同形——所以未标来历必须单列，不能并进「构造」。")
    unverified = [g for g, _, ref, _, v, _ in rows if v == "未验响过"]
    if unverified:
        print("  ★ 跑过但一次没响过：%s —— 这行不是好消息，是待查清单。" % unverified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
