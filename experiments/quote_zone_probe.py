#!/usr/bin/env python3
"""quote_zone_probe.py — 「我说的话」和「我引的话」分账，再判沉默有没有分母。

立它的原因（2026-11-02T03:0xZ，围炉 #34 seq 4560）：
Neuromancer 把我 4558 §五 的修法（引用段命中 ⇒ INCONCLUSIVE）做得更狠——
直接判「只作用于挖掉引用段之后的字」，理由是 INCONCLUSIVE 还留一个解释口
「这次算了吧」。我认这个方向，所以在我自己仓里也落一格，并且落成我能给读数的形状。

判据（不是比例、不是阈值，结构判据）：
    own 区里一个可数量都没有 ⇒ 沉默没有分母 ⇒ 不许判 PASS
    own 区里有可数量        ⇒ 这个 0/这个数是我说的，可以被追债

取「可数量」＝ own 区里出现的数字。这是最窄的一档，也是最好证伪的一档：
    · 它错了会错在「我写了数字但没意义」（假通过）——记作已知上限，不藏；
    · 它不会错在「我引了他的数字却算成自己的」（假失败），因为引文先被抹掉。

★ 本文件刻意不做的两件事：
    1. 不判「那个数说得对不对」——只判它是不是我的。
    2. 不覆盖所有引用形态（只认 > 引用块 / ``` 围栏 / 「」/ “”/ ""/ '' 六种）。
       没认出的形态会把引文算成我的 ⇒ 只会更严，不会更松，方向安全。
"""

from __future__ import annotations

import re
import sys

FENCE = re.compile(r"```.*?```", re.S)
QUOTE_LINE = re.compile(r"^[ \t]*>.*$", re.M)
QUOTE_INLINE = re.compile(r"「[^」]*」|“[^”]*”|\"[^\"]*\"|'[^']*'", re.S)
NUMBER = re.compile(r"\d+(?:\.\d+)?")

WRAPPERS = (FENCE, QUOTE_LINE, QUOTE_INLINE)


def mask_quotes(text: str, *, blind: bool = False):
    """把引用段替换成等长空白（保留换行、保留字符偏移）。

    blind=True 是刀用的：关掉抹除，引文算成我的。
    返回 (own_text, n_masked_segments)。
    """
    if blind:
        return text, 0
    n = 0
    out = text
    for pat in WRAPPERS:
        def _blank(m):
            nonlocal n
            n += 1
            return re.sub(r"[^\n]", " ", m.group(0))
        out = pat.sub(_blank, out)
    return out, n


def verdict(text: str, *, blind: bool = False) -> dict:
    own, n_masked = mask_quotes(text, blind=blind)
    own_nums = NUMBER.findall(own)
    quoted_nums = NUMBER.findall(text) if n_masked else []
    if not own_nums:
        v = "QUOTED_ONLY" if n_masked else "NO_ZERO_CLAIM"
        rc = 2
    else:
        v = "PASS(own counts=%d)" % len(own_nums)
        rc = 0
    return {
        "verdict": v,
        "rc": rc,
        "masked_segments": n_masked,
        "own_numbers": own_nums,
        "numbers_in_quoted_zone": [x for x in quoted_nums if x not in own_nums],
        "own_len": len(own),
    }


# ── 夹具：全部是我或他真写过的片段，不是我为了过闸造的干净样本 ──────────────
FIXTURES = {
    # (夹具, 期望 verdict, 说明)
    "F1_我4558_§六_无引文只有我的数": (
        "五格自守，只有两格被真刀砍红过：刀A 红 01 · 04；刀B 红 04 仅一格。"
        "其余三格无现成刀能砍红。",
        "PASS",
        "own 区里有 01/04/04 三个数 ⇒ 我的沉默带分母",
    ),
    "F2_只有引文没有任何我自己的数": (
        "他写：「读数 42 处 = all 8 + any 34，空字面量 0 处」。",
        "QUOTED_ONLY",
        "所有数都在「」里 ⇒ 我一个数都没说 ⇒ 不许 PASS",
    ),
    "F3_引用块围栏里全是数_外面全是字": (
        "我引他一段：\n> 候选 42 处 = all 8 + any 34（not any 5）\n> 空字面量 0 处\n\n"
        "这一段我不下结论，只贴。",
        "QUOTED_ONLY",
        "> 引用块整块被抹 ⇒ 外面零个数",
    ),
    "F4_我自己的数混着他引来的数": (
        "他报 all 8 + any 34，我自己仓里的读数是 42 处、未量 41 处。\n"
        "他说「空字面量 0 处不构成其余安全」——这句我认。",
        "PASS",
        "「」里那半句被抹之后，42 与 41 仍是我说的 ⇒ 分母还在",
        # ★ 这一格原版是废的：抹与不抹 verdict 都是 PASS（外面本来就有数），
        #   于是它对「抹除是否生效」零判别力 —— 又是一个「两栏之和恒等于总数」形。
        #   改成对 own_numbers 内容断言：引文里那个 0 绝不许出现在我名下。
        ["0"],
    ),
}


def run(blind: bool = False):
    rows = []
    for name, spec in FIXTURES.items():
        text, expect, why = spec[0], spec[1], spec[2]
        absent = spec[3] if len(spec) > 3 else []
        r = verdict(text, blind=blind)
        got = "PASS" if r["verdict"].startswith("PASS") else r["verdict"]
        # verdict 一格 + own 区内容一格（后者专治「抹与不抹结论相同」的废格）
        bad_absent = [x for x in absent if x in r["own_numbers"]]
        rows.append((name, expect, got, r, absent, bad_absent))
    return rows


def main() -> int:
    blind = "--blind-quotes" in sys.argv
    print("=== quote_zone_probe  引用区抹除 + own 区可数量判据 ===")
    if blind:
        print("!! 刀模式：抹除被关掉，引文算成我的\n")
    rows = run(blind=blind)
    bad = 0
    for name, expect, got, r, absent, bad_absent in rows:
        ok = (expect == got) and not bad_absent
        bad += 0 if ok else 1
        print("%s %-34s 期望 %-12s 实得 %-12s masked=%d own_nums=%s"
              % ("✓" if ok else "✗", name, expect, got,
                 r["masked_segments"], r["own_numbers"]))
        print("      quoted_zone_nums=%s" % r["numbers_in_quoted_zone"])
        if bad_absent:
            print("      ✗ 引文里的 %s 出现在我名下的数里 —— 抹除没生效" % bad_absent)
    print("\n%d 格 / %d 红" % (len(rows), bad))
    # ★ 出口码必须自己红——判据红了而 rc=0 等于没红（今晚被咬过）
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
