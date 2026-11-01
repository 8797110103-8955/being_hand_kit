#!/usr/bin/env python3
"""roster_extract.py — 解析 unittest -v 的 raw 输出，得到「名单 + 每格状态」。

为什么需要它：runner 自报的 `Ran 952 tests / FAILED (errors=19, skipped=39)` 只有总数，
拿不到「哪一格是 error、哪一格被 skip、skip 的理由是什么」。真相在逐行 raw 里。

## 病变层（2026-11-01 定）

行切分本来就对（HEAD 的 `def test_` 计数 952 与 runner 自报 952 逐字相等），
坏的是**状态词匹配层**。旧实现默认「状态词在 test 头那一行的行尾」，于是：

1. 测试自己 print 了东西时，状态词被顶到下一行、甚至再往下几行的行尾；
   若那个 print 带了换行，状态词会**独占一行**（前面没有 `... `）；
2. 前一格 print 不带换行时，下一格的头会被粘到上一格输出的行尾，不在行首；
3. 正文里出现 "skipped" 字样时，行尾匹配会把它认成状态词。

后果（旧读 vs 真值）：ok 738/894、skip 28/39、error 4/19，总数对、状态错，合计低估 19%。

## 修法

不按行、也不按行首切块。全文里把每个 `test_名 (tests.模块.类)` 出现处当锚点，
**按位置**切成段（锚点到下一个锚点），段内取**最后一个**状态词为这一格的状态。
锚点可以在行的任意位置；状态词也可以离锚点任意远——位置上不携带信息，顺序才携带。

两处第二次修的（2026-11-01 13:5xZ）：
- **去重键必须是 (名字, 模块)**，不是名字。全仓 952 个 `def test_` 但只有 936 个**唯一**名字，
  按名字去重会把 16 个同名不同类的格吞掉（total 936 ≠ 952）。
- 状态词有两种形状：行尾「… ... ok」，和**独占一行**的 `ok`（测试 print 带换行时）。

## 读数契约

  python3 tools/roster_extract.py <raw.txt>
  rc 0 = 名单与 runner 自报汇总行**逐字相等**
  rc 1 = 不等（打印逐项 diff + 只在一边出现的名字）
  rc 2 = 找不到汇总行（没有第二读数，不能判绿）

第二读数原则：raw 里 runner 自己打的 `Ran N tests` + `FAILED (errors=E, skipped=S)`
是我无法改写的外部读数；本工具的名单必须与它逐字相等才算过。自算数与装置同源时，
一致性只证明我没改错自己——所以两数必须来自不同来源（runner 打的 vs 我解析的）。
"""
import re
import sys
import collections

ANCHOR = re.compile(r"(test_\w+) \((tests\.[\w.]+)\)")
CUT = re.compile(r"^(?:={20,}|Ran \d+ tests?|ERROR: |FAIL: )", re.M)
_WORDS = r"(ok|FAIL|ERROR|skipped(?::| ).*?|expected failure|unexpected success)"
STATUS = re.compile(
    r"\.\.\. " + _WORDS + r"(?=\s*$|\s*\n)"      # 形状一：输出行尾
    r"|^" + _WORDS + r"\s*$",                     # 形状二：独占一行
    re.M,
)
SUMMARY_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
SUMMARY_DETAIL = re.compile(r"^(OK|FAILED)(?: \((.*)\))?\s*$", re.M)


def classify(status):
    if not status:
        return "UNKNOWN"
    s = status.strip()
    if s == "ok":
        return "ok"
    if s.startswith("skipped"):
        return "skip"
    if s == "ERROR":
        return "error"
    if s == "FAIL":
        return "fail"
    return "other"


def main(path):
    text = open(path, errors="replace").read()

    anchors = []
    seen = set()
    for m in ANCHOR.finditer(text):
        key = (m.group(1), m.group(2))
        if key in seen:      # 汇总段的 ERROR:/FAIL: 块会重复名字，只取首次
            continue
        seen.add(key)
        anchors.append((m.start(), key))

    roster = {}
    for idx, (pos, key) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(text)
        seg = text[pos:end]
        c = CUT.search(seg, 1)
        if c:
            seg = seg[: c.start()]
        hits = STATUS.findall(seg)
        status = None
        for h in reversed(hits):                     # 最后一个状态词
            status = next((g for g in h if g), None)
            if status:
                break
        roster[key] = status

    counts = collections.Counter(classify(v) for v in roster.values())
    skip_reasons = collections.Counter(
        v.strip()[:70] for v in roster.values() if classify(v) == "skip"
    )

    print(f"file: {path}")
    print(f"roster total = {len(roster)}  (unique names: {len({k[0] for k in roster})})")
    for k in ("ok", "skip", "error", "fail", "other", "UNKNOWN"):
        if counts.get(k):
            print(f"  {k:8s} = {counts[k]}")
    if counts.get("UNKNOWN"):
        unk = [k for k, v in roster.items() if classify(v) == "UNKNOWN"]
        print(f"  未判出状态 {len(unk)} 格（前 10）：")
        for n, mod in unk[:10]:
            print(f"    - {n}  ({mod})")
    print("skip reasons:")
    for reason, n in skip_reasons.most_common():
        print(f"  {n:4d}  {reason}")

    # ★ 纸面检查（2026-11-01T20:2xZ）：值域比结局窄的一格。
    #   roster 抽出 0 格、runner 也说 Ran 0 tests 时，两边相等 ⇒ 走到
    #   「ALL EQUAL — 逐字相等」rc=0。**没测到 与 测过且为零，同一个读数。**
    #   同族第四例的同一形状（我自己的规则：空结果要 rc=9，不许安静地对账成功）。
    if not roster:
        print("!! roster 抽出 0 格 —— 空结果不许读成全等（rc=9）")
        print("   判据：0 格既可能是「这文件真没有 test」，也可能是「我的抽取器认不出它了」；")
        print("   两者在这里同形。要么给分母（summary 报了几格且 >0），要么拒绝出结论。")
        return 9

    m_ran = SUMMARY_RAN.search(text)
    m_det = SUMMARY_DETAIL.search(text[m_ran.end():]) if m_ran else None
    if not (m_ran and m_det):
        print("!! 找不到 runner 汇总行 —— 没有第二读数，不能判绿（rc=2）")
        return 2
    total = int(m_ran.group(1))
    detail = dict((k, int(v)) for k, v in re.findall(r"(\w+)=(\d+)", m_det.group(2) or ""))
    want = {
        "total": total,
        "ok": total - detail.get("errors", 0) - detail.get("failures", 0) - detail.get("skipped", 0),
        "skip": detail.get("skipped", 0),
        "error": detail.get("errors", 0),
        "fail": detail.get("failures", 0),
    }
    got = {
        "total": len(roster),
        "ok": counts.get("ok", 0),
        "skip": counts.get("skip", 0),
        "error": counts.get("error", 0),
        "fail": counts.get("fail", 0),
    }
    print(f"summary line: Ran {total} tests / {m_det.group(1)} ({m_det.group(2)})")
    print("compare:")
    bad = []
    for k in ("total", "ok", "skip", "error", "fail"):
        same = got[k] == want[k]
        if not same:
            bad.append(k)
        print(f"  {'OK ' if same else 'BAD'} {k:6s} roster={got[k]:5d}  summary={want[k]:5d}")
    if bad:
        print(f"!! MISMATCH in {bad}")
        errheads = set(re.findall(r"^(?:ERROR|FAIL): (test_\w+) \(", text, re.M))
        roster_err = {k[0] for k, v in roster.items() if classify(v) == "error"}
        print(f"   error 名字：roster={len(roster_err)} 汇总段={len(errheads)}  "
              f"只在roster={sorted(roster_err - errheads)[:3]} "
              f"只在汇总段={sorted(errheads - roster_err)[:3]}")
        return 1
    print("ALL EQUAL — 名单与 runner 汇总行逐字相等")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
