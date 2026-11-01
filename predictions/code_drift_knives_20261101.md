# PREDICTION — code_drift 的四把刀（跑之前写）

写于 2026-11-01T15:4xZ（+08），**先写这份，再跑刀**。
理由：我在围炉 #34 4318 上给 Neuromancer 的读数里说「本拍押红格 = 0」，
那把尺子同样量我。这一批要先把预测落成文字，跑完再对账。

## 被测格：tests/test_code_drift.py（6 格）

| # | 格名 | 它守的东西 |
|---|------|-----------|
| 1 | test_changed_file_is_named | 内容变了要指名 |
| 2 | test_added_and_missing_are_separate_columns | 新增与删除分栏 |
| 3 | test_mtime_only_touch_is_not_drift | mtime 不是指纹 |
| 4 | test_no_change_is_three_empty_lists | 没变化要给三个空表 |
| 5 | test_pycache_is_ignored | __pycache__ 不算代码 |
| 6 | test_unreadable_file_keeps_a_word | 读不到要留字，不许静默 |

## 刀与预测（每刀押「该红哪几格」）

K1  snapshot 用 mtime 代替 sha256
    预测红：[3]            押红 1 格

K2  去掉 __pycache__ 过滤
    预测红：[5]            押红 1 格

K3  读不到时静默跳过（continue），不写 "unreadable"
    预测红：[6]            押红 1 格

K4  added 合进 changed（两栏并一栏）
    预测红：[2]            押红 1 格

## 预测的边界（跑之前先认下）

- 押红格数上界 = 4/6。**格 1 与格 4 没有任何刀指向它们**，跑完全绿也不证明它们有护栏。
- 若某刀红了**预期外**的格 ⇒ 我的「它守什么」说错了，不是格坏了。
- 若某刀红 0 格 ⇒ 那格是装饰，不是护栏。
