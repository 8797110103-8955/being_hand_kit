"""Live acceptance: the text= path reads dpr once, too (0.13.8).

Neuromancer's fourth site. Same lying page as the selector-path test: the
getter answers 2 on the first read, 1 after. Old shape — JS multiplies by its
own read (2), driver re-reads (1) and divides by it → dispatch at CSS 560. New
shape — one read, carried → 280,180 and the page's own log says x=280.

Run with HAND_CDP_PORT=9444 against an isolated Chrome.
"""
import json
import sys
import time
import urllib.parse

sys.path.insert(0, "/home/alice/Hand")
from hand.action import cdp_act
from hand.perception import cdp_core

HTML = """<!doctype html><meta charset=utf-8><style>
body{margin:0}
#t{position:absolute;left:240px;top:160px;width:80px;height:40px}
</style>
<button id=t>go</button>
<script>
var n = 0;
Object.defineProperty(window, 'devicePixelRatio', {
  get: function () { n += 1; window.__reads = n; return n === 1 ? 2 : 1; }
});
window.__log = [];
document.addEventListener('click', function (e) {
  window.__log.push({x: e.clientX, y: e.clientY, target: e.target.id,
                     trusted: e.isTrusted, reads_at_click: window.__reads});
}, true);
</script>
"""


def main():
    url = "data:text/html;charset=utf-8," + urllib.parse.quote(HTML)
    idx, page = cdp_core.resolve_page(None, cdp_core.list_pages())
    ws = cdp_core.cdp_connect(page["webSocketDebuggerUrl"])
    try:
        cdp_core.cdp_call(ws, "Page.navigate", {"url": url}, timeout=15)
    finally:
        ws.close()
    time.sleep(1.0)

    out = cdp_act.cdp_click_do("text=go")
    ev = out.get("evidence") or {}
    print("receipt: result=%s verified=%s" % (out.get("result"), out.get("verified")))
    print("  click_point:", json.dumps(ev.get("click_point"), sort_keys=True))
    print("  dispatch:", json.dumps(ev.get("dispatch"), sort_keys=True))

    idx, page = cdp_core.resolve_page(None, cdp_core.list_pages())
    ws = cdp_core.cdp_connect(page["webSocketDebuggerUrl"])
    try:
        r = cdp_core.cdp_call(ws, "Runtime.evaluate",
                              {"expression":
                               "JSON.stringify({log:window.__log, reads:window.__reads})",
                               "returnByValue": True}, timeout=10)
        print("page says:", r["result"]["value"])
        page_says = json.loads(r["result"]["value"])
    finally:
        ws.close()

    # 0.13.8 (2026-11-03): 这一段原来只印读数，没有判据 —— 入口块 sys.exit(main())
    # 是 11-01 加的，但它守的是一个恒返回 None 的函数 ⇒ rc 恒 0。
    # 「有东西决定退出码」与「那个东西判不判」是两个洞，前一个修完这个还在。
    cp = ev.get("click_point") or {}
    logs = page_says.get("log") or []
    first = logs[0] if logs else {}
    checks = [
        ("click_point.x==280", cp.get("x") == 280.0),
        ("click_point.y==180", cp.get("y") == 180.0),
        ("page.reads==1", page_says.get("reads") == 1),
        ("page.log[0].x==280", first.get("x") == 280),
        ("page.log[0].reads_at_click==1", first.get("reads_at_click") == 1),
        ("page.log[0].trusted is True", first.get("trusted") is True),
    ]
    for name, ok in checks:
        print("  [%s] %s" % ("ok" if ok else "FAIL", name))
    passed = all(ok for _, ok in checks)
    print("verdict:", "PASS" if passed else "FAIL")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
