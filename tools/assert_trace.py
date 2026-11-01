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

TARGET = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "test_code_drift.py"))
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# 正控：测试数读不到就不许报绿。这条是被自己抓出来的——
# 脚本以 tools/ 为 sys.path[0] 跑时，loadTestsFromName 静默变成一个 _FailedTest，
# 于是 rc=1、asserts=[] 同时成立，看起来像「装置正常但什么都没测到」。


_records = {}       # (test, lineno, method) -> hit count
assert_methods = ("assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
                  "assertIn", "assertNotIn", "assertIsNone", "assertIsNotNone",
                  "assertGreater", "assertGreaterEqual", "assertLess", "assertLessEqual",
                  "assertIs", "assertIsNot", "assertIsInstance", "assertAlmostEqual")


def _wrap(orig, name):
    def wrapper(self, *a, **k):
        f = inspect.currentframe().f_back
        if os.path.abspath(f.f_code.co_filename) == TARGET:
            key = (self._testMethodName, f.f_lineno, name)
            _records[key] = _records.get(key, 0) + 1
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
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_code_drift")
    with open(os.devnull, "w") as devnull:
        res = unittest.TextTestRunner(resultclass=FirstRed, stream=devnull).run(suite)
    # 落点回读：报告**被测进程实际 import 的那份文件**的 sha，
    # 不是「我以为我写的那份」。两者不是同一个事实——
    # 「我写了」与「它读到的是那份」之间隔着 .pyc 缓存、cwd、sys.path、
    # 写在了读之后。Neuromancer 10-31 v1 就是这么栽的（import 主探针 ⇒
    # 他改的那份没被执行，读数「没变化」)。
    import hashlib
    try:
        import kit.mcp_server as _M
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
    }
    # 正控：真跑到了才许给读数。零测试 + 零 assert 必须响，不许安静。
    if res.testsRun == 0 or not _records:
        out["rc"] = 9
        out["fatal"] = "no tests / no asserts recorded — 装置没被测到，不是通过"
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
