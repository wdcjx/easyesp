#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则级单测：每条规则一个最小片段，validator --format json 断言命中规则 ID。
- 出现 R0 = 消息措辞与 RULE_TABLE 失配（消息不许随手改，改了必须同步 RULE_TABLE）
- 未命中该规则 / result 与预期不符 = 该规则检测路径回归（esp_event 静默失效教训）
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VAL = os.path.join(ROOT, "scripts", "validate_esp_generated.py")

CASES = {  # 规则 ID -> (片段, 期望 result)
    "R1":  (["rule_snippets/r1_isr_no_iram.c"],        "FAIL"),
    "R2":  (["rule_snippets/r2_nonvolatile.c"],        "FAIL"),
    "R3":  (["rule_snippets/r3_isr_no_fromisr.c"],     "FAIL"),
    "R4":  (["rule_snippets/r4_isr_task_api.c"],       "FAIL"),
    "R5":  (["rule_snippets/r5_isr_printf.c"],         "FAIL"),
    "R6":  (["rule_snippets/r6_yield_noarg.c"],        "FAIL"),
    "R7":  (["rule_snippets/r7_wait_no_timeout.c"],    "PASS"),
    "R8":  (["rule_snippets/r8_task_malloc.c"],        "PASS"),
    "R9":  (["rule_snippets/r9_stack_bytes.c"],        "FAIL"),
    "R10": (["rule_snippets/r10_nvs_order.c"],         "FAIL"),
    "R11": (["rule_snippets/r11_arduino_loop_block.ino"], "FAIL"),
    "R12": (["rule_snippets/r12_legacy_driver.c"],     "PASS"),
    "R13": (["rule_snippets/r13_rs485_de.c"],          "FAIL"),
    "R14": (["rule_snippets/r14_esp_event_block.c"],   "FAIL"),
    "R15": (["rule_snippets/r15_espnow_cb_malloc.c"],  "FAIL"),
    "M1":  (["rule_snippets/m1_bad_target.c"],         "FAIL"),
    "M2":  (["rule_snippets/m2_gpio_missing.c"],       "FAIL"),
    "M3":  (["rule_snippets/m3_dup_pin.c"],            "FAIL"),
    "M4":  (["rule_snippets/m4_undeclared_gpio.c"],    "PASS"),
    "M5":  (["project_conflict/a.c", "project_conflict/b.c"], "FAIL"),
    "M6":  (["target_conflict/a.c", "target_conflict/b.c"],   "FAIL"),
}


def main():
    fails = []
    for rid, (files, expect) in CASES.items():
        paths = [os.path.join(HERE, f) for f in files]
        r = subprocess.run([sys.executable, VAL, "--format", "json"] + paths,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        errs = []
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            errs.append("输出不是 JSON: " + r.stdout[:100])
            d = None
        if d:
            rules = {f["rule"] for f in d["findings"]}
            if "R0" in rules:
                errs.append("出现 R0（消息措辞与 RULE_TABLE 失配）")
            if rid not in rules:
                errs.append(f"未命中（实际 {sorted(rules)}）")
            if d["result"] != expect:
                errs.append(f"result={d['result']} 期望 {expect}")
        status = "PASS" if not errs else "FAIL"
        print(f"[{status}] 规则 {rid}")
        for e in errs:
            print(f"        {e}")
            fails.append(rid)
    print(f"-- 规则单测: {len(CASES)} 条, 失败 {len(set(fails))} --")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
