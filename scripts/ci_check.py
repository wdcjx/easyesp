#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 回归：validator 判定基线 + 仓库一致性检查。

本地可跑：python scripts/ci_check.py（在仓库根目录执行）。
CI 中由 .github/workflows/ci.yml 调用，exit 0 = 全部通过。

检查项：
  1. validator 十一样本基线（五 bad_sample 必须 FAIL 且违规/警告数精确匹配，
     六正例必须 PASS 且违规=0）——防规则漂移（误报/漏报都会被抓住）
  2. references/ 目录与 SKILL.md 资源表双向一致（表里有的文件必须存在；
     目录里的文档必须都在表中）
  3. known-pitfalls.md 坑编号连续 1..N（无重号/跳号；表格格式 `| N |`）
  4. README.md 中坑计数声明 == known-pitfalls.md 实际条数（防忘更新）
  5. README.md 知识文档计数声明 == references/ 实际 .md 数
  6. README.md 文件树覆盖 references/ 全部文档（防新增文档忘加文件树行）

  真实编译验证（idf.py build 三目标 + arduino-cli 三板）在
  .github/workflows/build.yml——本脚本只做静态一致性回归。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAL = os.path.join(ROOT, 'scripts', 'validate_esp_generated.py')

# (相对路径, 预期判定, 预期 VIOLATION, 预期 WARNING)
BASELINE = [
    ('tests/bad_sample_isr.c',                       'FAIL', 12, 1),
    ('tests/bad_sample_task.c',                      'FAIL', 4,  2),
    ('tests/bad_sample_ble.cpp',                     'FAIL', 5,  1),
    ('tests/manifest_bad_sample.c',                  'FAIL', 2,  1),
    ('tests/bad_sample_rs485.c',                     'FAIL', 1,  1),
    ('tests/good_sample_ble.cpp',                    'PASS', 0,  0),
    ('tests/manifest_good_sample.c',                 'PASS', 0,  0),
    ('templates/main_idf.c',                         'PASS', 0,  0),
    ('templates/main_arduino.ino',                   'PASS', 0,  0),
    ('examples/blink_uart_demo/main/blink_uart_demo.c', 'PASS', 0, 0),
    ('examples/arduino_blink_uart/arduino_blink_uart.ino', 'PASS', 0, 0),
]

failures = []


def check(name, ok, detail=''):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ''))
    if not ok:
        failures.append(name)


# ---------- 1. validator 基线 ----------
for rel, verdict, exp_v, exp_w in BASELINE:
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        check(f"validator: {rel} 存在", False, '文件缺失')
        continue
    r = subprocess.run([sys.executable, VAL, path],
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    m = re.search(r'违规\(VIOLATION\):\s*(\d+)\s+警告\(WARNING\):\s*(\d+)', r.stdout)
    v = re.search(r'结果:\s*(PASS|FAIL)', r.stdout)
    got_verdict = v.group(1) if v else '?'
    got_v = int(m.group(1)) if m else -1
    got_w = int(m.group(2)) if m else -1
    ok = (got_verdict == verdict and got_v == exp_v and got_w == exp_w)
    check(f"validator: {rel} -> {verdict} V={exp_v} W={exp_w}",
          ok, f"实际 {got_verdict} V={got_v} W={got_w}" if not ok else '')

# ---------- 2. references <-> SKILL.md 资源表 ----------
skill_path = os.path.join(ROOT, 'SKILL.md')
skill = open(skill_path, encoding='utf-8').read()
listed = set(re.findall(r'`(references/[A-Za-z0-9._-]+\.md)`', skill))
actual = {f'references/{f}' for f in os.listdir(os.path.join(ROOT, 'references'))
          if f.endswith('.md')}
missing_files = sorted(listed - actual)
unlisted = sorted(actual - listed)
check('SKILL.md 资源表 -> 文件存在', not missing_files,
      f'表中有但文件缺失: {missing_files}' if missing_files else '')
check('references/ 文件全部登记在 SKILL.md', not unlisted,
      f'未登记: {unlisted}' if unlisted else '')

# ---------- 3. known-pitfalls 编号连续（表格格式 | N | 症状 | 根因 | 修法 |） ----------
kp_path = os.path.join(ROOT, 'references', 'known-pitfalls.md')
kp = open(kp_path, encoding='utf-8').read()
nums = [int(n) for n in re.findall(r'^\| (\d+) \|', kp, re.M)]
expected_seq = list(range(1, len(nums) + 1))
check(f'known-pitfalls 编号连续 1..{len(nums)}', nums == expected_seq,
      f'实际序列异常（重号/跳号）: {nums}' if nums != expected_seq else '')

# ---------- 4. README 坑计数一致 ----------
readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
declared = set(int(n) for n in re.findall(r'(\d+)\s*条坑清单', readme))
declared |= set(int(n) for n in re.findall(r'坑清单\D*?(\d+)\s*条', readme))
check(f'README 坑计数声明 == 实际 {len(nums)} 条',
      declared == {len(nums)},
      f'声明值 {sorted(declared)} != 实际 {len(nums)}' if declared != {len(nums)} else '')

# ---------- 5. README 知识文档计数一致 ----------
ref_count = len(actual)
declared_refs = set(int(n) for n in re.findall(r'(\d+)\s*份知识文档', readme))
check(f'README 知识文档计数声明 == 实际 {ref_count} 份',
      declared_refs == {ref_count},
      f'声明值 {sorted(declared_refs)} != 实际 {ref_count}' if declared_refs != {ref_count} else '')

# ---------- 6. README 文件树覆盖 references 全部文档 ----------
readme_md_names = set(re.findall(r'([a-z0-9][a-z0-9-]*\.md)', readme))
ref_names = {f for f in os.listdir(os.path.join(ROOT, 'references'))
             if f.endswith('.md')}
not_in_readme = sorted(ref_names - readme_md_names)
check('README 文件树覆盖 references 全部文档', not not_in_readme,
      f'README 未提及: {not_in_readme}' if not_in_readme else '')

print()
if failures:
    print(f"CI 结果: FAIL（{len(failures)} 项未过）")
    sys.exit(1)
print('CI 结果: PASS（全部通过）')
