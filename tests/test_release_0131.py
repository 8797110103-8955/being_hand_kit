"""Release test for 0.13.1 — 帧内点击的坐标系。

Spec: CHANGELOG 0.13.1 条目。这一版修的是一处「两套坐标系被当成一套」：

  0.13.0 把子 frame 的节点并进了 a11y 树，`cdp_see` 画的坐标是对的
  （`DOM.getBoxModel` 给的就是顶层坐标）；但 `cdp_click_handle` 走的是另一条
  读法——`getBoundingClientRect` 与 `elementFromPoint` 探针都在**节点自己那个
  frame 的坐标系**里，读出来直接派发。iframe 在 (8, 59.4) 的夹具上，那就是
  61px 的纵向偏差：点落在 frame 自己的 padding 上，frame 不跳转，而回执写着
  result=ok / resolved=true / landed=true（探针确实在帧内验到了目标）。

  行为证明见 tests/test_iframe_coords.py（点完 frame 必须真的跳到 B）。
  本文件锁版本、变更记录与契约的公开面。
"""

import json
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _manifest():
    with open(os.path.join(ROOT, "kit", "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


class TestVersion0131(unittest.TestCase):
    """Historical lock: 0.13.1 shipped 2026-10-22. The version itself has moved
    on — current-version assertions live in test_release_0132."""

    def test_changelog_has_0131_entry(self):
        self.assertIn("## [0.13.1]", _read("CHANGELOG.md"))


class TestFrameTranslation(unittest.TestCase):
    """The translation must exist, be fallible in the safe direction, and be
    inert on the main frame (0.13.0's behaviour for every non-frame page)."""

    def test_helpers_exist(self):
        from hand.action import cdp_act
        for name in ("_main_frame_id", "_node_frame_id",
                     "_frame_content_origin", "_dispatch_offset"):
            self.assertTrue(callable(getattr(cdp_act, name, None)), name)

    def test_main_frame_is_zero_offset(self):
        from hand.action import cdp_act
        calls = []

        def fake_call(ws, method, params, msg_id=None, timeout=None):
            calls.append(method)
            if method == "Page.getFrameTree":
                return {"frameTree": {"frame": {"id": "ROOT"}}}
            if method == "DOM.describeNode":
                return {"node": {"frameId": "ROOT"}}
            raise AssertionError(f"unexpected call {method}")

        with mock.patch.object(cdp_act, "cdp_call", fake_call):
            dx, dy, fid, err = cdp_act._dispatch_offset(object(), object())
        self.assertEqual((dx, dy), (0.0, 0.0))
        self.assertIsNone(err)
        self.assertNotIn("DOM.getFrameOwner", calls,
                         "a main-frame node must not trigger a frame lookup")

    def test_unreadable_frame_refuses_instead_of_dispatching(self):
        """A child-frame node whose origin cannot be read is an error, never a
        silent frame-local dispatch (that is the 0.13.0 defect)."""
        from hand.action import cdp_act

        def fake_call(ws, method, params, msg_id=None, timeout=None):
            if method == "Page.getFrameTree":
                return {"frameTree": {"frame": {"id": "ROOT"}}}
            if method == "DOM.describeNode":
                return {"node": {"frameId": "CHILD"}}
            if method == "DOM.getFrameOwner":
                raise RuntimeError("boom")
            raise AssertionError(f"unexpected call {method}")

        with mock.patch.object(cdp_act, "cdp_call", fake_call):
            dx, dy, fid, err = cdp_act._dispatch_offset(object(), object())
        self.assertEqual(fid, "CHILD")
        self.assertTrue(err, "a frame-local point must not be dispatchable")
        self.assertEqual((dx, dy), (0.0, 0.0))

    def test_frame_origin_reads_the_owner_content_box(self):
        """The offset is the owner's CONTENT box (border/padding excluded)."""
        from hand.action import cdp_act

        def fake_call(ws, method, params, msg_id=None, timeout=None):
            if method == "DOM.getFrameOwner":
                return {"backendNodeId": 4}
            if method == "DOM.getBoxModel":
                return {"model": {"border": [120, 80, 360, 80, 360, 200, 120, 200],
                                  "content": [122, 82, 358, 82, 358, 198, 122, 198]}}
            raise AssertionError(f"unexpected call {method}")

        with mock.patch.object(cdp_act, "cdp_call", fake_call):
            self.assertEqual(cdp_act._frame_content_origin(object(), "CHILD"),
                             (122.0, 82.0))


class TestHandleCarriesFrameId(unittest.TestCase):
    """cdp_see must say which frame a merged node came from — a handle that
    does not cannot be clicked correctly in any version."""

    def test_handle_entries_are_tagged_from_the_merge(self):
        from hand.perception import ax_tree
        src = _read("hand/perception/ax_tree.py")
        self.assertIn('entry["frame_id"] = frame_of_bid[bid]', src)
        self.assertIn("frame_of_bid[bnid] = fid", src)

    def test_bidless_frame_nodes_are_declared(self):
        """Merged ≠ addressable: a line without a backend id gets a note.

        0.13.4 moved the count from raw AX nodes to printed lines and reworded
        the note ("readable here, but not aimable"), so this pins the *contract*
        — a note exists and it is derived from the frame bookkeeping — not the
        0.13.1 sentences, which outlived their truth.

        2026-11-01T21:2xZ 收紧（围炉 #34 4439 §四 送到我仓里的一刀）：
        原来两条都是 `assertIn(名字, 源码)`。数了一遍 `frame_lines_without_handle`
        在整份文件里出现 6 次：3 处真代码、3 处在字符串里；而在**被测那个函数**
        `ax_snapshot` 的源码里只有 2 次、且**两次都在字符串里**（读 ser 的键）。
        ⇒ 把那段计算整块删掉，这条格照样绿：它钉住的是一个**读者**，不是这个数
        怎么算出来的。改成整模块 AST，两件事都要成立：
          ① 有人给这个名字赋过非常量的值（计算存在）
          ② 序列化字典里键与值指向同一个名字（算出来的那个数真的被写出去）
        """
        import ast
        from hand.perception import ax_tree
        import inspect
        mod_src = inspect.getsource(ax_tree)
        tree = ast.parse(mod_src)
        assigned = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "frame_lines_without_handle" in names:
                    assigned.append(node.value)
            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name) and \
                        node.target.id == "frame_lines_without_handle":
                    assigned.append(node.value)
        self.assertTrue(assigned, "整模块里没有任何一处给 frame_lines_without_handle "
                                  "赋值 —— 它只以字符串形式残留")
        self.assertFalse(all(isinstance(v, ast.Constant) for v in assigned),
                         "它只被赋了常量 —— 不是从 frame 记账里算出来的")
        wired = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and \
                            k.value == "frame_lines_without_handle" and \
                            isinstance(v, ast.Name) and \
                            v.id == "frame_lines_without_handle":
                        wired.append(v)
        self.assertTrue(wired, "算出来的那个数没有被写进序列化字典 —— "
                               "键在、值不是它，回执上的数就不是它")
        src = inspect.getsource(ax_tree.ax_snapshot)
        self.assertIn("merged into this tree", src)


if __name__ == "__main__":
    unittest.main()
