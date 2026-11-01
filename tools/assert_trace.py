#!/usr/bin/env python3
"""断言轨迹：一格里面到底有哪几条 assert 真被执行到了。

为什么（2026-11-01，围炉 #34 seq 4334）：
    Neuromancer 说纵向那层（格内有几条 assert）他的装置零视野——刀矩阵只吃
    红=[格名]，格内结构完全不可见。他说这不是缺刀，是装置换不了轴。
    我把轴换掉：不数红格，数 **assert 调用**。

做法：把 unittest.TestCase 的断言方法包一层，记下每次调用发生在
     tests/test_code_drift.py 的第几行、哪条方法、有没有抛。
    于是「格 × assert 行号」是实测出来的，不是读源码数出来的。

两列读数，两件事：
    hit         —— 干净跑时这条 assert 真被执行到（可达性）
    first_red   —— 在某个变异下，这一格的**第一条**失败 assert 是哪条
                   （判别性：能不能当"判据响了"的那个响）

一条 assert 如果 hit 但从不 first_red，它就在别人红了之后永远到不了
——不承重，但在文件里跟真判据长得一模一样。

只用一个进程跑一次（不改源码）；变异由外面 driver 换盘后重跑本脚本。
"""
import inspect
import json
import os
import sys
import unittest

# 可测性（2026-11-01）：用具自身必须有测试，否则它坏掉时没人喊。
# 三个环境变量把「被测谁」从硬编码里拿出来，自检才能喂假夹具：
#   ASSERT_TRACE_ROOT     仓库根（默认本文件上一级）
#   ASSERT_TRACE_TARGET   TARGET 文件（默认 <root>/tests/test_code_drift.py）
#   ASSERT_TRACE_MODULE   要加载的测试模块名（默认 tests.test_code_drift）
#   ASSERT_TRACE_SUBJECT  落点回读时 import 的对象（默认 kit.mcp_server）
_ROOT = os.path.abspath(os.environ.get("ASSERT_TRACE_ROOT")
                        or os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.abspath(os.environ.get("ASSERT_TRACE_TARGET")
                         or os.path.join(_ROOT, "tests", "test_code_drift.py"))
TARGET_MODULE = os.environ.get("ASSERT_TRACE_MODULE", "tests.test_code_drift")
SUBJECT_MODULE = os.environ.get("ASSERT_TRACE_SUBJECT", "kit.mcp_server")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# 正控：测试数读不到就不许报绿。这条是被自己抓出来的——
# 脚本以 tools/ 为 sys.path[0] 跑时，loadTestsFromName 静默变成一个 _FailedTest，
# 于是 rc=1、asserts=[] 同时成立，看起来像「装置正常但什么都没测到」。


_records = {}       # (test, lineno, method) -> hit count（本文件内）
_external = {}       # (test, file, lineno, method) -> hit count（本文件外，必须报）
_args = {}          # (test, lineno, method) -> 第一次调用的实参 repr（值面：样本上这两个值是否恒等）
assert_methods = ("assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
                  "assertIn", "assertNotIn", "assertIsNone", "assertIsNotNone",
                  "assertGreater", "assertGreaterEqual", "assertLess", "assertLessEqual",
                  "assertIs", "assertIsNot", "assertIsInstance", "assertAlmostEqual")


def _wrap(orig, name):
    def wrapper(self, *a, **k):
        f = inspect.currentframe().f_back
        fn = os.path.abspath(f.f_code.co_filename)
        if fn == TARGET:
            key = (self._testMethodName, f.f_lineno, name)
            _records[key] = _records.get(key, 0) + 1
            # 值面：只记第一次的实参。为的是事后能问「这两个被断言的值，
            # 在这套样本上是不是恒等」——恒等则格分不开，刀红也不分。
            if key not in _args:
                _args[key] = [repr(x)[:90] for x in a[:4]]
        else:
            # 不在本文件里的断言：**不许静默丢掉**。
            # 丢掉它意味着「这一格的判据有一部分我看不见」，而看不见和全绿同形。
            # 记下来、报出来、让 rc 响——把「静默丢样本」变成「可见的另一种状态」。
            key = (self._testMethodName, os.path.relpath(fn, os.path.dirname(TARGET)), f.f_lineno, name)
            _external[key] = _external.get(key, 0) + 1
        return orig(self, *a, **k)
    wrapper.__name__ = name
    return wrapper


def patch():
    for name in assert_methods:
        if hasattr(unittest.TestCase, name):
            setattr(unittest.TestCase, name, _wrap(getattr(unittest.TestCase, name), name))


class FirstRed(unittest.TextTestResult):
    """每格第一条抛 AssertionError 的行号（在 tests/test_code_drift.py 里）。"""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.first_red = {}

    def _note(self, test, err):
        line, tb = None, err[2]
        while tb:
            if os.path.abspath(tb.tb_frame.f_code.co_filename) == TARGET:
                if line is None:
                    line = tb.tb_lineno
            tb = tb.tb_next
        self.first_red.setdefault(test._testMethodName, line)

    def addFailure(self, test, err):
        self._note(test, err)
        super().addFailure(test, err)

    def addError(self, test, err):
        self._note(test, err)
        super().addError(test, err)


def main():
    patch()
    suite = unittest.defaultTestLoader.loadTestsFromName(TARGET_MODULE)
    with open(os.devnull, "w") as devnull:
        res = unittest.TextTestRunner(resultclass=FirstRed, stream=devnull).run(suite)
    # 值面：把每一格每条 assert 的实参印出来。判「样本退化」时不用再读源码，
    # 也就不用凭记忆——凭记忆的那一次我在 17:4x 已经错过一次。
    print("\n== 值面（每条 assert 的实参，第一次调用）==")
    for (test, line, meth), vs in sorted(_args.items()):
        print("  %-58s L%-4d %-16s %s"
              % (test[:58], line, meth, " | ".join(vs)))

    # 行号也要回读：把该行的源码原文一并印出来。
    # 只印行号的话，「红在 L137」是我说的；带上原文，它能被对方核。
    src = open(TARGET, encoding="utf-8").read().splitlines()
    fr = getattr(res, "first_red", {}) or {}
    if fr:
        print("\n== first_red 回读（行号 + 该行原文）==")
        for test, line in sorted(fr.items()):
            txt = src[line - 1].strip() if line and line <= len(src) else "<行号越界>"
            print("  %-48s %-4s %s" % (test[:48], line, txt[:100]))

    # 落点回读：报告**被测进程实际 import 的那份文件**的 sha，
    # 不是「我以为我写的那份」。两者不是同一个事实——
    # 「我写了」与「它读到的是那份」之间隔着 .pyc 缓存、cwd、sys.path、
    # 写在了读之后。Neuromancer 10-31 v1 就是这么栽的（import 主探针 ⇒
    # 他改的那份没被执行，读数「没变化」)。
    import hashlib
    try:
        _M = __import__(SUBJECT_MODULE, fromlist=["__file__"])
        _mf = os.path.abspath(_M.__file__)
        _msha = hashlib.sha256(open(_mf, "rb").read()).hexdigest()[:8]
    except Exception as e:  # noqa: BLE001
        _mf, _msha = None, "import_failed:%s" % e
    out = {
        "rc": 0 if res.wasSuccessful() else 1,
        "tests_run": res.testsRun,
        "module_file": _mf,
        "module_sha": _msha,
        "asserts": [{"test": t, "line": l, "method": m, "hits": c}
                    for (t, l, m), c in sorted(_records.items())],
        "first_red": {k: v for k, v in res.first_red.items() if v is not None},
        "external_asserts": [{"test": t, "file": fl, "line": l, "method": m, "hits": c}
                             for (t, fl, l, m), c in sorted(_external.items())],
    }
    # 正控：真跑到了才许给读数。零测试 + 零 assert 必须响，不许安静。
    # 多条理由必须并列上报（2026-11-01 自检抓到的真 bug）：两条闸同时响时，
    # 后写的 fatal 会盖掉前一条的**理由**——于是回执说了「响了」，说错了
    # 「为什么响」。同族：一个 fatal 字段装两件事，等于把两个读数压成一个。
    fatals = []
    if _external:
        fatals.append("asserts outside TARGET — 这一格的判据有一部分不在我的视野里，不算全绿")
    if res.testsRun == 0 or not _records:
        fatals.append("no tests / no asserts recorded — 装置没被测到，不是通过")
    if fatals:
        out["rc"] = 9
        out["fatal"] = "; ".join(fatals)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
