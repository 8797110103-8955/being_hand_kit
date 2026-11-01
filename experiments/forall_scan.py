#!/usr/bin/env python3
"""forall_scan.py — 找 all()/any()/not-any 的真实调用点，并按「空集可达性」分栏。

纪律（2026-11-02 深夜，围炉 #34）：
  形状命中是候选，不是结论。
  all ∅ ⇒ True 印「全部通过」；any ∅ ⇒ False 印「啥也没发现」——阅读端同向。
  两栏必须分开报，且每栏要自报分母。

用法：python3 experiments/forall_scan.py [root]
只读，不改任何文件。
"""
import ast
import sys
from pathlib import Path

SKIP_DIRS = {".venv", ".venv312", "node_modules", "__pycache__", ".git", "build", "dist"}


def iter_py(root: Path):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def call_name(node):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def is_not(node):
    return isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)


def iterable_of(node):
    """返回被迭代的那个表达式（all(X for ...) / all(X) / any(X ...)）。"""
    if not node.args:
        return None
    a = node.args[0]
    if isinstance(a, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return a.generators[0].iter if a.generators else None
    return a


def denom_kind(it):
    """粗略判「分母此刻多长」，只给静态可见的那几类，其余 UNKNOWN。"""
    if it is None:
        return "NO_ARGS"
    if isinstance(it, (ast.List, ast.Tuple, ast.Set)):
        n = len(it.elts)
        return f"LITERAL n={n}" + ("  ← 空字面量！" if n == 0 else "")
    if isinstance(it, ast.Dict):
        n = len(it.keys)
        return f"LITERAL n={n}" + ("  ← 空字面量！" if n == 0 else "")
    if isinstance(it, ast.Constant):
        return f"CONST {it.value!r}"
    if isinstance(it, ast.Name):
        return f"NAME {it.id}"
    if isinstance(it, ast.Call):
        return f"CALL {call_name(it) or '?'}()"
    if isinstance(it, ast.Attribute):
        return f"ATTR .{it.attr}"
    if isinstance(it, ast.BinOp):
        return "BINOP"
    return type(it).__name__.upper()


def scan_call_walk_only(root: Path):
    """只走 Call 一遍、不做 NOT-ANY 第二遍 —— 用来交叉验证两条发现路径。

    为什么需要它：`not any(...)` 由两条互不依赖的路径各发现一次
    （Call walk 认它是 any，UnaryOp walk 认它是 not-any）。
    **两条路径互不依赖 ⇒ 一条死了另一条照样绿。**
    2026-11-02 实测：把 Call walk 里的 "any" 摘掉（刀B），
    整套自守格只红了基线那一格，而「not any ⊆ any」那格一声不响。
    """
    out = set()
    for p in sorted(iter_py(root)):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) in ("all", "any"):
                out.add((str(p), getattr(node, "lineno", 0), call_name(node)))
    return out


def scan(root: Path):
    rows = []  # (path, lineno, kind, negated, denom, src)
    for p in sorted(iter_py(root)):
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(p))
        except (SyntaxError, ValueError) as e:
            rows.append((p, 0, "PARSE_ERROR", False, "", str(e)[:60]))
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node)
            if name not in ("all", "any"):
                continue
            it = iterable_of(node)
            lineno = getattr(node, "lineno", 0)
            raw = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
            rows.append((p, lineno, name, False, denom_kind(it), raw))
        # not any(...) —— 单独走一遍 UnaryOp，因为它的洞方向和 all ∅ 不同
        for node in ast.walk(tree):
            if not isinstance(node, ast.UnaryOp) or not isinstance(node.op, ast.Not):
                continue
            inner = node.operand
            if not isinstance(inner, ast.Call) or call_name(inner) != "any":
                continue
            it = iterable_of(inner)
            lineno = getattr(inner, "lineno", 0)
            raw = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
            rows.append((p, lineno, "any", True, denom_kind(it), raw))
    # 去重：同一个 Call 节点会走两遍（all/any 走一遍、not any 又走一遍），
    # 不去重会把 5 处 not any 数成 10 处。
    # 读数：v1 印「总候选 47」，去重后 42 —— 差 5，正好是 not any 的处数。
    # （我先在注释里写了 6/41，是照着输出随手数的，错了。8 + 34 = 42 才是对得上账的那一对。）
    dedup = {}
    for r in rows:
        key = (str(r[0]), r[1], r[2])
        if key not in dedup or r[3]:  # NOT-ANY 优先覆盖普通行
            dedup[key] = r
    return list(dedup.values())


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    rows = scan(root)
    if not rows:
        print("FORALL_SCAN: 0 处 —— 但这是「我没扫到」，不是「没有」。先确认 root=%s" % root)
        return 2

    buckets = {}
    for r in rows:
        buckets.setdefault(r[2], []).append(r)

    print(f"FORALL_SCAN root={root}")
    print(f"总候选 {len(rows)} 处（**候选，不是洞**）\n")
    for kind in ("all", "any", "PARSE_ERROR"):
        rs = buckets.get(kind, [])
        if not rs:
            continue
        print(f"=== {kind}( {len(rs)} 处 ===")
        for p, ln, k, neg, d, raw in rs:
            flag = "NOT-ANY" if neg else ""
            print(f"  {p}:{ln}  {flag:<8} {d:<22} {raw[:70]}")
        print()

    literal_empty = [r for r in rows if "空字面量" in r[4]]
    unknown = [r for r in rows if not r[4].startswith(("LITERAL", "CONST"))]
    print("--- 分母读数 ---")
    print(f"  空字面量（空集必然可达）：{len(literal_empty)}")
    print(f"  分母非静态可见（UNKNOWN，需人工判空集可达性）：{len(unknown)} / {len(rows)}")
    print(f"  其余（LITERAL/CONST 非空，空集走不到）：{len(rows) - len(unknown) - len(literal_empty)}")
    print()
    print("注意：本条扫描看不见 sum(...)==0 与手写 for+标志变量。"
          f"「{len(literal_empty)} 处空字面量」不构成「其余都安全」——未量的 {len(unknown)} 处才是主体。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
