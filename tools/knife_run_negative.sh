#!/usr/bin/env bash
# 空读数正控：让 knife_run 在一轮注定读到坏数据的运行里跑一次，验证它拒绝出结论。
#
# 为什么（2026-11-01T18:4xZ，围炉 #34 seq 4392→4393）：
# 我给每道闸配「响过没有」之后，落点栏响了——但只到「响」，没到「改过结论」。
# 实测：把 ASSERT_TRACE_ROOT 指到一份预变异的临时树，被测工具在每一把刀上都崩掉
# （TARGET 解析到假根下、FileNotFoundError），十格全是 UNPARSED，
# 而汇总段照样印出「空刀 0 / 类数 0 / 同红组 1 组（十把并成一组）」、rc=0。
# 一个从未被测到的世界，被印成了「测过，结论是零」——比假绿更坏，因为它带着汇总的样子。
#
# 现在：任一格不是解析出来的回执 ⇒ RUN INVALID，汇总跳过，rc=9。
# 这个脚本就是那条例的外壳——两个方向都验（干净要出结论、污染要拒绝出结论），
# 只验一个方向的话，把汇总段整个删掉也能「通过」。
#
# Readers：改过 knife_run 汇总段的人。不进 tests/run_tests.py 的 MODULES，
# 理由：它跑两次真刀集（约 2×40s），比整个标准套件还慢；它验的是报表纪律，不是被测代码。
set -u
cd "$(dirname "$0")/.." || exit 1
fails=0

echo "== 方向一 干净跑：必须出结论 =="
out=$(python3 tools/knife_run.py 2>&1); rc=$?
echo "$out" | grep -qE "^  类数 test粒度" && echo "  类数行 有 ✓" || { echo "  类数行 缺 ✗"; fails=1; }
[ "$rc" -eq 0 ] && echo "  rc=0 ✓" || { echo "  rc=$rc（期望 0）✗"; fails=1; }

echo "== 方向二 污染跑：必须拒绝出结论 =="
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/kit" && cp kit/mcp_server.py "$tmp/kit/" || exit 1
out=$(PYTHONPATH="$PWD" ASSERT_TRACE_ROOT="$tmp" python3 tools/knife_run.py 2>&1); rc=$?
echo "$out" | grep -q "RUN INVALID" && echo "  RUN INVALID ✓" || { echo "  没报 INVALID ✗"; fails=1; }
if echo "$out" | grep -qE "^  类数 test粒度"; then echo "  仍然印了类数 ✗（空读数与测过同形）"; fails=1; else echo "  没印类数 ✓"; fi
[ "$rc" -eq 9 ] && echo "  rc=9 ✓" || { echo "  rc=$rc（期望 9）✗"; fails=1; }

[ "$fails" -eq 0 ] && echo "== 两向都过 ==" || echo "== 有 ✗ =="
exit $fails
