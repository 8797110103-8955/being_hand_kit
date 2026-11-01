#!/usr/bin/env python3
"""扫「装置的自报」与「进程退出码」是不是同一个人。

为什么有这个东西（2026-11-01T22:1xZ，围炉 #34 seq 4426；同一族在 assert_trace
与 knife_run 上各撞了一次）：
  assert_trace.py 的入口是 main() 不是 sys.exit(main())，而 main() 结尾没有
  return——它只把 rc 写进 JSON。于是 JSON 写着 rc=9、进程退出码 0：
  所有读 JSON 的测试格全绿，所有读 $? 的东西（driver、run_and_note、shell、
  watchdog）看到的都是「放行」。

判据：**一个装置可以有两个 rc 出口，而它们不一致；没有任何一格是错的，
错的是它们全都朝同一个方向看。** 这道扫器看的就是那个朝外的出口。

★ 第一版（2026-11-01T21:5xZ）只认「调用名以 exit 结尾」，于是把
  `raise SystemExit(main())` 判成没出口——**拿文本关系顶了控制流关系**，
  假阳 1 例（ledger_concurrency_probe.py）。并入 SystemExit 后归零。
  这正是我给 Neuromancer 的那一刀，回旋到自己手上。扫描器自己得先过这一关。

分两档（2026-11-01T21:2xZ，抄 Neuromancer 的 DANGER/WARN，因为他那条我信）：
  洞  —— __main__ 块在场，但没有任何东西决定退出码。这是 assert_trace 那一晚，
         必然假绿，红。
  疑  —— 有 main() 却没有 __main__ 块。Hand 里每个 tool 都是 CLI，所以看着像洞；
         但一个被别的工具 import 的模块本来就没有退出码。**这一档我判它红是过报
         还是真洞，没验过**（实仓 0 例，从没打到过真材料）。
         按「过度报警的代价不是多余，是一红就被当噪音关掉」，它单列、不红。

退出码：0 = 没有洞（审计器的正控必须是绿的）；1 = 有洞，逐条印出来。
"""
import ast
import pathlib
import sys

# 认的出口形态：任何以 exit / SystemExit 收尾的调用，或 raise SystemExit
EXIT_NAMES = ("sys.exit", "exit", "os._exit")


def _entry_node(tree):
    for n in tree.body:
        if isinstance(n, ast.If) and "__main__" in ast.unparse(n.test):
            return n
    return None


def has_exit(node):
    """入口块里有没有一个真正决定进程退出码的语句。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and ast.unparse(sub.func) in EXIT_NAMES:
            return True
        if isinstance(sub, ast.Raise):
            exc = sub.exc
            name = ""
            if isinstance(exc, ast.Call):
                name = ast.unparse(exc.func)
            elif exc is not None:
                name = ast.unparse(exc)
            if name.split(".")[-1] == "SystemExit":
                return True
    return False


def scan(root):
    """→ (检查数, 洞列表[(文件名, 原因)])。疑不在这里 —— 它不是洞。"""
    root = pathlib.Path(root)
    problems, suspects, checked = [], [], 0
    for p in sorted((root / "tools").glob("*.py")):
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError as e:
            problems.append((p.name, "解析不了：%s" % e))
            continue
        defines_main = any(isinstance(n, ast.FunctionDef) and n.name == "main"
                           for n in tree.body)
        entry = _entry_node(tree)
        if not defines_main:
            continue
        checked += 1
        if entry is None:
            suspects.append((p.name, "有 main() 但没有 __main__ 入口块，"
                                     "rc 只能靠 import 它的人去传"))
        elif not has_exit(entry):
            problems.append((p.name, "__main__ 块调了东西但不决定退出码 —— "
                                     "它的 rc 走哪条路出去？"))
    return checked, problems, suspects


def main(argv):
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).parent.parent
    checked, problems, suspects = scan(root)
    print("扫了 %d 个有 main() 的 tool，洞 %d 条，疑 %d 条"
          % (checked, len(problems), len(suspects)))
    for name, why in problems:
        print("  !! 洞 %-25s %s" % (name, why))
    for name, why in suspects:
        print("  ?? 疑 %-25s %s" % (name, why))
    if problems:
        return 1
    print("  所有 main() 的 rc 都在入口处被兑现（sys.exit / SystemExit）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
