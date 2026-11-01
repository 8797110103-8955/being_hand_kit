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


def note(guard, action, detail=""):
    """action: "ran"（正常放行）/ "refused"（拒绝出结论）。写失败不许让闸崩。"""
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "guard": guard, "action": action, "detail": str(detail)[:200]}
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return rec


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
        g = agg.setdefault(r.get("guard", "?"), {"ran": 0, "refused": 0, "last_refused": None})
        if r.get("action") == "refused":
            g["refused"] += 1
            g["last_refused"] = r.get("ts")
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
        rows.append((g, v["ran"], v["refused"], v["last_refused"], verdict))
    return rows


def main():
    rows = table(load())
    if not rows:
        print("闸台账：空（%s）" % _path())
        print("  ⇒ 没有一道闸记过账。这不是「全部正常」，是「全部未验」。")
        return 0
    print("闸台账（%s）" % _path())
    print("  %-16s %5s %5s  %-20s %s" % ("闸", "跑", "响不过", "上次响", "判定"))
    for g, ran, ref, last, verdict in rows:
        print("  %-16s %5d %5d  %-20s %s" % (g, ran, ref, last or "-", verdict))
    unverified = [g for g, _, ref, _, v in rows if v == "未验响过"]
    if unverified:
        print("  ★ 跑过但一次没响过：%s —— 这行不是好消息，是待查清单。" % unverified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
