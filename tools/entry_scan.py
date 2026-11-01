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
  洞  —— 两条，都红：
         a) __main__ 块在场，但没有任何东西决定退出码（assert_trace 那一晚）
         b) 有 main()、无入口块、**却在模块顶层裸调 main()**
            —— 这是我原以为「没有退出码」的那一档，看了实物才知道它跑得起来：
               跑得起来、rc 恒 0（里面成不成立都不影响 $?）、且 **import 它就执行**。
               实仓样本 ×3（tests/live/live_dpr_{once,old_ab}、live_text_dpr），
               已加守卫。这就是 Neuromancer 说「我这边造不出来」的那个样本 ——
               它一直在我的视野之外，因为这道扫器只 glob tools/。
  疑  —— 有 main()、无入口块、也没有裸调 ⇒ 可能是一个被 import 的模块，本来就不该有
         退出码。这一档我不替它决定，只列出来；它不红。

★ 视野校验（2026-11-01T21:2xZ，Neuromancer 还我的一条）：扫到 0 个目标文件时
  **报红 rc=2**，不报「0 处问题」——否则「我没扫到东西」和「我扫完干净」同形。
  这一版视野从 tools/ 扩到 tools/ + tests/live/：**扫描面本身是可以过窄的，
  过窄的扫描面和干净的扫描面在回执上一模一样。**

退出码：0 = 没有洞；1 = 有洞，逐条印出来；2 = 视野为空，拒绝给结论。
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


# ★ 每个视野分量带自己的锚（2026-11-01T21:5xZ，围炉 #34 seq 4447 之后）：
#   一个锚只守得住它所在的那个分量。我上一个版本只有一个锚（tools/entry_scan.py），
#   于是 tests/live 那个分量**整个坏掉与它本来就是空的同形** ——
#   锚在场的绿会盖住第二个分量消失的红。
#   ⇒ 判据：**共用一个锚的多分量视野，坏掉一个分量的形状与那个分量本来就空同形。**
#     每个分量都要有自己的锚；锚的失效模式必须是「拒绝给结论」，不能是「放行」。
VIEWS = (("tools", "entry_scan.py"), ("tests/live", "live_dpr_once.py"))
# ★ 自锚（2026-11-01T21:4xZ，围炉 #34 seq 4445 → 之后）：
#   视野校验只查「扫到 0 个」太弱 —— 扫到一个不相关的文件它照样放行，
#   于是「我看着的是一堆文件」与「我看着的是我该看的那些」依旧同形。
#   加一个类别判据（不是数量判据）：**视野里必须有我自己这个文件**。
#   它是我唯一能百分百断言「一定存在且一定该被扫到」的东西。
#   ⇒ 判据形状：视野校验要用「一个必然在场的锚」，不用节点数/文件数阈值。
#     数量阈值（≥3 个进程、≥2 层）会把「合法的窄视野」判成「视野不成立」。
VIEW_NAMES = tuple(v for v, _ in VIEWS)


def _bare_main_call(tree):
    """模块顶层有没有一句裸 main()（没有 __main__ 守卫）。"""
    for n in tree.body:
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            if ast.unparse(n.value.func) == "main":
                return True
    return False


def _view_files(root):
    files = []
    for v, _anchor in VIEWS:
        files.extend(sorted((root / v).glob("*.py")))
    return files


def missing_anchors(root):
    """每个视野分量的锚在不在被扫集合里。→ [(分量, 锚路径), …]（空 = 全在）"""
    root = pathlib.Path(root)
    seen_files = set(_view_files(root))
    out = []
    for view, anchor in VIEWS:
        a = root / view / anchor
        if a not in seen_files:
            out.append((view, a))
    return out


def scan(root):
    """→ (看得见的文件数, 检查数, 洞列表, 疑列表)。"""
    root = pathlib.Path(root)
    problems, suspects, checked, seen = [], [], 0, 0
    for p in _view_files(root):
        seen += 1
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
            if _bare_main_call(tree):
                problems.append((p.name, "顶层裸调 main()：跑得起来，但 rc 恒 0，"
                                         "而且 import 它就执行"))
            else:
                suspects.append((p.name, "有 main() 但没有 __main__ 入口块，"
                                         "也没有裸调 —— 可能本就该被 import"))
        elif not has_exit(entry):
            problems.append((p.name, "__main__ 块调了东西但不决定退出码 —— "
                                     "它的 rc 走哪条路出去？"))
    return seen, checked, problems, suspects


def main(argv):
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).parent.parent
    seen, checked, problems, suspects = scan(root)
    missing = missing_anchors(root)
    if missing:
        for view, a in missing:
            print("!! REFUSED 视野分量 %-11s 的锚不在视野里：%s" % (view, a))
        print("   —— 一个分量坏掉，与它本来就是空的同形；共用一个锚守不住第二个分量")
        return 2
    if seen == 0:
        print("!! REFUSED 视野为空：%s 下一个 .py 都没扫到 —— 这是「没扫到东西」，"
              "不是「扫完干净」" % (root,))
        return 2
    print("看了 %d 个文件（%s，每分量锚在场），其中 %d 个有 main()，洞 %d 条"
          % (seen, " + ".join(VIEW_NAMES), checked, len(problems)))
    # ★ 0 例的档位不等于判对（2026-11-01T21:4xZ）：空档印「未覆盖」，
    #   不印「疑 0 条」——后者读起来和「疑档判得准」一模一样。
    if suspects:
        print("  疑 %d 条：%s" % (len(suspects), [x[0] for x in suspects]))
    else:
        print("  疑 0 条 —— **本档未覆盖**（0 例只说明没材料，不说明档位对）")
    for name, why in problems:
        print("  !! 洞 %-25s %s" % (name, why))
    for name, why in suspects:
        print("  ?? 疑 %-25s %s" % (name, why))
    if problems:
        return 1
    print("  所有 main() 的 rc 都在入口处被兑现（sys.exit / SystemExit）")
    print("  ★ 这句只在我刚印的「看了 N 个文件」之上才成立 —— 分母是视野，不是结论")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
