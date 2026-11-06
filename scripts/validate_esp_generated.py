#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_esp_generated.py — ESP32（ESP-IDF / Arduino）生成代码工程纪律检查（启发式静态检查）

用法：
    python validate_esp_generated.py main.c bsp_sensor.c ...    # 检查指定 .c/.ino 文件
    python validate_esp_generated.py --dir output/              # 递归检查目录下全部 .c/.ino/.cpp/.h

退出码：0 = 无 VIOLATION（WARNING 允许存在）
        1 = 存在 VIOLATION（必须全部修复后才能交付）
        2 = 用法错误 / 无文件可检查

说明：
  - 启发式检查：WARNING 需人工逐条确认；本工具不能替代 idf.py build 编译与上板验证。
  - 多文件工程请把应用代码全部一起传入（nvs/WiFi 顺序跨文件核对；managed_components、
    build、.pio、third_party、libraries 等厂商/产物目录自动跳过）。
  - "真 ISR"识别依据（三者之一，详见 references/isr-and-concurrency-rules.md 铁律 A）：
      1) 定义带 IRAM_ATTR；2) 名字含 isr/irq；3) 被本文件中的注册调用登记
      （gpio_isr_handler_add / attachInterrupt / uart_isr_register / gptimer .on_alarm=）。
    esp_timer 回调、esp_event 处理器、ESP-NOW 回调按"任务上下文回调"（铁律 B）单独检查阻塞。
  - 自测：python validate_esp_generated.py ../tests/bad_sample_isr.c ../tests/bad_sample_task.c
    应报多条 VIOLATION；../templates/main_idf.c 应 PASS。
"""

import argparse
import re
import sys
from pathlib import Path

VIOL = "VIOLATION"
WARN = "WARNING "

KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "default", "break",
    "continue", "return", "goto", "sizeof", "static", "volatile", "const",
    "void", "int", "char", "long", "short", "unsigned", "signed", "float",
    "double", "struct", "union", "enum", "typedef", "extern", "register",
    "bool", "true", "false", "NULL", "inline",
}

FUNC_RE = re.compile(
    r"(?m)^(?:static\s+)?(?:[A-Za-z_]\w*[\s\*]+)+(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^;{}]*)\)\s*\{"
)  # 返回类型与 IRAM_ATTR/ICACHE_RAM_ATTR 等属性可任意多 token，函数名=最后一个 token
DECL_RE = re.compile(
    r"(?m)^(?:static\s+)?(?:const\s+)?(?P<vol>volatile\s+)?"
    r"(?:unsigned\s+|signed\s+)?(?:[A-Za-z_]\w*[\s\*]+)+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=[^;\n]*)?;"
)

# 真 ISR 注册调用：捕获被登记的函数名（铁律 A 证据）
REGISTRATION_RES = [
    re.compile(r"\bgpio_isr_handler_add\s*\(\s*[A-Za-z_]\w*\s*,\s*(?:&\s*)?([A-Za-z_]\w*)"),
    re.compile(r"\battachInterrupt\s*\([^,]+,\s*(?:&\s*)?([A-Za-z_]\w*)\s*,"),
    re.compile(r"\buart_isr_register\s*\(\s*[A-Za-z_]\w*\s*,\s*(?:&\s*)?([A-Za-z_]\w*)"),
    re.compile(r"\.on_alarm\s*=\s*(?:&\s*)?([A-Za-z_]\w*)"),          # gptimer_event_callbacks_t
    re.compile(r"\btimer_isr_callback_add\s*\([^,]+,[^,]+,\s*(?:&\s*)?([A-Za-z_]\w*)"),  # 旧 timer group
]
# 任务上下文回调（铁律 B）：esp_timer / esp_event / ESP-NOW
TASKCB_REGISTRATION_RES = [
    re.compile(r"\.callback\s*=\s*(?:&\s*)?([A-Za-z_]\w*)"),          # esp_timer_create_args_t
    re.compile(r"\besp_timer_start_(?:once|periodic)\s*\(\s*[A-Za-z_]\w*\s*,\s*(?:&\s*)?([A-Za-z_]\w*)"),
    re.compile(r"\besp_now_register_(?:recv|send)_cb\s*\(\s*(?:&\s*)?([A-Za-z_]\w*)"),
    re.compile(r"\besp_event_handler_register(?:_with)?\s*\([^;]*?,\s*&?([A-Za-z_]\w*)"),
    re.compile(r"\besp_http_client_register_event_handler\s*\([^,]+,\s*&?([A-Za-z_]\w*)"),
]

# 任务级 FreeRTOS API → FromISR 版本；None = 无 FromISR 版本，中断内绝对禁止
# （ESP-IDF 的 FreeRTOS API 名与 STM32 移植版一致）
RTOS_TASK_API_MAP = {
    "xQueueSend": "xQueueSendFromISR",
    "xQueueSendToFront": "xQueueSendToFrontFromISR",
    "xQueuePeek": "xQueuePeekFromISR",
    "xQueueReceive": "xQueueReceiveFromISR",
    "xQueueGenericSend": "xQueueGenericSendFromISR",
    "xSemaphoreGive": "xSemaphoreGiveFromISR",
    "xSemaphoreTake": "xSemaphoreTakeFromISR",
    "xTaskNotify": "xTaskNotifyFromISR",
    "xTaskNotifyAndQuery": "xTaskNotifyAndQueryFromISR",
    "xTaskNotifyGive": "vTaskNotifyGiveFromISR",
    "xEventGroupSetBits": "xEventGroupSetBitsFromISR",
    "xEventGroupClearBits": None,          # 无 FromISR 版本
    "xStreamBufferSend": "xStreamBufferSendFromISR",
    "xMessageBufferSend": "xMessageBufferSendFromISR",
    "vTaskResume": "xTaskResumeFromISR",
    "vTaskPrioritySet": None,
    "vTaskDelete": "vTaskDeleteFromISR" if False else "xTaskDeleteFromISR",  # IDF: xTaskDelete? 见下
    "vTaskDelay": None,
    "vTaskDelayUntil": None,
    "vTaskSuspend": None,
    "xTaskCreate": None,
    "xTaskCreatePinnedToCore": None,
}
# ESP-IDF 实际 API：任务里删任务用 vTaskDelete；中断里没有 FromISR 版——中断内禁删任务。
RTOS_TASK_API_MAP["vTaskDelete"] = None

# FromISR API（反向：任务上下文禁止）
FROMISR_API_RE = re.compile(r"\b([A-Za-z_]\w*FromISR)\s*\(")

# 真 ISR 内的阻塞/违规调用
ISR_BLOCK_CALL_RE = re.compile(
    r"(?i)\b(vTaskDelay|vTaskDelayUntil|ets_delay_us|delay|delayMicroseconds|"
    r"printf|puts|sprintf|snprintf|scanf|gets|ESP_LOG[EWIDV])\b"
)
ISR_HEAP_RE = re.compile(r"\b(malloc|calloc|realloc|free)\s*\(")
ISR_NVS_RE = re.compile(r"\b(nvs_set_\w+|nvs_commit|nvs_erase(?:_key|_all)?)\s*\(")
ISR_WIFI_RE = re.compile(r"\besp_wifi_\w+\s*\(")

TASKCB_BLOCK_RE = re.compile(
    r"(?i)\b(vTaskDelay|ets_delay_us|delay|delayMicroseconds)\s*\("
)

ARDUINO_BAN_CALL_RE = re.compile(r"(?i)\b(delay|delayMicroseconds|yield|vTaskDelay)\s*\(")


def blank_keep_newlines(match):
    return re.sub(r"[^\n]", " ", match.group(0))


def neutralize(text):
    """注释和字符串替换为等长空白，保留行号与偏移。"""
    text = re.sub(r"/\*.*?\*/", blank_keep_newlines, text, flags=re.S)
    text = re.sub(r"//[^\n]*", blank_keep_newlines, text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', blank_keep_newlines, text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", blank_keep_newlines, text)
    return text


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def match_brace(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(s) - 1


def match_paren(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(s) - 1


def split_top_args(s):
    """按顶层逗号拆分实参列表文本。"""
    args, depth, cur = [], 0, []
    for ch in s:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return args


def in_spans(pos, spans):
    return any(a <= pos <= b for a, b in spans)


def analyze(path, text, findings, irq_owner, project):
    fname = path.name

    def add(line, level, msg):
        findings.append((fname, line, level, msg))

    # ---- 函数与全局变量收集 ----
    funcs = []
    for m in FUNC_RE.finditer(text):
        open_idx = m.end() - 1
        close_idx = match_brace(text, open_idx)
        funcs.append({
            "name": m.group("name"),
            "params": m.group("params"),
            "sig": text[m.start(): open_idx],
            "start": m.start(),
            "open": open_idx,
            "close": close_idx,
            "body": text[open_idx + 1: close_idx],
        })

    spans = sorted((f["start"], f["close"]) for f in funcs)
    globals_list = []  # (name, is_volatile, line)
    prev = 0
    for s, e in spans:
        seg = text[prev:s]
        for dm in DECL_RE.finditer(seg):
            if dm.group(0).lstrip().startswith("extern"):
                continue
            globals_list.append(
                (dm.group("name"), bool(dm.group("vol")), line_of(text, prev + dm.start("name")))
            )
        prev = e + 1
    for dm in DECL_RE.finditer(text[prev:]):
        if dm.group(0).lstrip().startswith("extern"):
            continue
        globals_list.append(
            (dm.group("name"), bool(dm.group("vol")), line_of(text, prev + dm.start("name")))
        )

    # ---- ISR / 任务回调分类 ----
    reg_gpio = set()
    reg_attach = set()
    reg_uart = set()
    reg_gptimer = set()
    for r in REGISTRATION_RES[:1]:
        reg_gpio |= set(r.findall(text))
    for r in REGISTRATION_RES[1:2]:
        reg_attach |= set(r.findall(text))
    for r in REGISTRATION_RES[2:3]:
        reg_uart |= set(r.findall(text))
    for r in REGISTRATION_RES[3:]:
        reg_gptimer |= set(r.findall(text))
    registered = reg_gpio | reg_attach | reg_uart | reg_gptimer
    task_cbs = set()
    for r in TASKCB_REGISTRATION_RES:
        task_cbs |= set(r.findall(text))

    def is_true_isr(f):
        n = f["name"]
        if "IRAM_ATTR" in f["sig"]:
            return True
        if re.search(r"(?i)(isr|irq)", n):
            # 排除初始化/管理类函数（button_isr_init、gpio_isr_service_install 等不是中断处理函数）
            if re.search(r"(?i)(_init|_install|_setup|_register|_enable|_disable|_config|_add|_remove|_create|_attach)$", n):
                pass
            else:
                return True
        if n in registered:
            return True
        return False

    isr_funcs = [f for f in funcs if is_true_isr(f)]
    cb_funcs = [f for f in funcs if f["name"] in task_cbs and not is_true_isr(f)]
    isr_spans = [(f["open"], f["close"]) for f in isr_funcs]
    isr_names = {f["name"] for f in isr_funcs}

    # 去重（同函数可能既 IRAM_ATTR 又被注册）
    seen = set()
    isr_funcs = [f for f in isr_funcs if not (f["name"] in seen or seen.add(f["name"]))]

    # ---- R1: 注册 ISR 的 IRAM_ATTR ----
    iram_service = re.search(r"\bgpio_install_isr_service\s*\(\s*[^)]*ESP_INTR_FLAG_IRAM", text)
    attach_reg = bool(re.search(r"\battachInterrupt\s*\(", text))
    for f in isr_funcs:
        if "IRAM_ATTR" in f["sig"]:
            continue
        line = line_of(text, f["start"])
        if f["name"] in reg_attach and attach_reg:
            add(line, VIOL,
                f"attachInterrupt 注册的 ISR '{f['name']}' 缺少 IRAM_ATTR：Arduino core 运行期"
                "会断言崩溃（Cache disabled but cached memory region access），ISR 必须 IRAM_ATTR")
        elif f["name"] in reg_gpio and iram_service:
            add(line, VIOL,
                f"gpio_install_isr_service(ESP_INTR_FLAG_IRAM) 下注册的 ISR '{f['name']}' "
                "缺少 IRAM_ATTR：flash 写期间 cache 被禁用，非 IRAM ISR 触发即 crash")
        elif f["name"] in registered or any("IRAM" in fl for fl in project["flags"]):
            add(line, WARN,
                f"ISR '{f['name']}' 缺少 IRAM_ATTR：若可能挂 ESP_INTR_FLAG_IRAM 或在 flash "
                "操作窗口触发，必须放 IRAM；确认过不会的才可接受")

    # ---- R2/R3/R4/R5: 真 ISR 纪律 ----
    for f in isr_funcs:
        body = f["body"]
        line0 = line_of(text, f["start"])
        calls = set(re.findall(r"([A-Za-z_]\w*)\s*\(", body))
        used = set(re.findall(r"[A-Za-z_]\w*", body)) - calls - KEYWORDS
        # R2 volatile（调用点行号）
        for g_name, g_vol, g_line in globals_list:
            if g_name in used and not g_vol:
                um = re.search(r"\b%s\b" % re.escape(g_name), body)
                uline = line_of(text, f["open"] + 1 + um.start()) if um else line0
                add(uline, VIOL,
                    f"ISR '{f['name']}' 访问了非 volatile 全局变量 '{g_name}'"
                    f"（声明于本文件第 {g_line} 行）：与中断共享的变量必须 volatile")
        # R3 FromISR（调用点行号）
        for cm in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            cname = cm.group(1)
            if cname not in RTOS_TASK_API_MAP:
                continue
            cline = line_of(text, f["open"] + 1 + cm.start())
            repl = RTOS_TASK_API_MAP[cname]
            if repl is None:
                add(cline, VIOL,
                    f"ISR '{f['name']}' 调用 '{cname}()'：无 FromISR 版本，"
                    "中断内禁止延时/阻塞/建任务，应置标志由任务处理")
            else:
                add(cline, VIOL,
                    f"ISR '{f['name']}' 调用了任务级 API '{cname}()'："
                    f"必须改用 '{repl}()'，并配合 portYIELD_FROM_ISR(woken)")
        # R4 阻塞/堆/NVS/WiFi
        for cm in ISR_BLOCK_CALL_RE.finditer(body):
            add(line_of(text, f["open"] + 1 + cm.start()), VIOL,
                f"ISR '{f['name']}' 内调用阻塞/打印 '{cm.group(1)}'：中断内禁止延时/printf/ESP_LOG/忙等")
        for hm in ISR_HEAP_RE.finditer(body):
            add(line_of(text, f["open"] + 1 + hm.start()), VIOL,
                f"ISR '{f['name']}' 内使用动态内存 '{hm.group(1)}()'：中断内禁止堆操作")
        for nm in ISR_NVS_RE.finditer(body):
            add(line_of(text, f["open"] + 1 + nm.start()), VIOL,
                f"ISR '{f['name']}' 内写 NVS '{nm.group(1)}()'：flash 写会禁用 cache，"
                "与 IRAM ISR 互斥，必须置标志由任务处理")
        for wm in ISR_WIFI_RE.finditer(body):
            add(line_of(text, f["open"] + 1 + wm.start()), VIOL,
                f"ISR '{f['name']}' 内调用 '{wm.group(0).rstrip('(')}'：esp_wifi API 不可在中断内调用")
        # R5 临界区变体
        for pm in re.finditer(r"\bport(ENTER|EXIT)_CRITICAL\s*\(", body):
            add(line_of(text, f["open"] + 1 + pm.start()), VIOL,
                f"ISR '{f['name']}' 内用了 port{pm.group(1)}_CRITICAL：中断侧必须用 "
                f"port{pm.group(1)}_CRITICAL_ISR")
        # while 轮询
        for wm in re.finditer(r"\bwhile\s*\(", body):
            op2 = wm.end() - 1
            cp2 = match_paren(body, op2)
            cond2 = body[op2 + 1: cp2].strip()
            if cond2 in ("1", "0", "!0", "true"):
                continue
            add(line_of(text, f["open"] + 1 + wm.start()), WARN,
                f"ISR '{f['name']}' 内存在 while 轮询：请确认为事件驱动或有时限保证")

    # ---- R5 反向: 任务上下文用 _ISR 临界区 ----
    for f in funcs:
        if f["name"] in isr_names:
            continue
        for pm in re.finditer(r"\bport(ENTER|EXIT)_CRITICAL_ISR\s*\(", f["body"]):
            add(line_of(text, f["open"] + 1 + pm.start()), VIOL,
                f"任务函数 '{f['name']}' 内用了 port{pm.group(1)}_CRITICAL_ISR：任务侧必须用 "
                f"port{pm.group(1)}_CRITICAL")

    # ---- R3 反向: 任务上下文用 FromISR ----
    for f in funcs:
        if f["name"] in isr_names or f["name"] in task_cbs:
            continue
        for fm in FROMISR_API_RE.finditer(f["body"]):
            add(line_of(text, f["open"] + 1 + fm.start()), VIOL,
                f"任务函数 '{f['name']}' 调用 '{fm.group(1)}()'：FromISR API 只能在中断上下文调用")

    # ---- R6: portYIELD_FROM_ISR 用法 ----
    for m in re.finditer(r"\bportYIELD_FROM_ISR\s*\(\s*\)", text):
        add(line_of(text, m.start()), VIOL,
            "portYIELD_FROM_ISR() 缺参数：ESP32 上必须传入 woken 变量——"
            "portYIELD_FROM_ISR(xHigherPriorityTaskWoken)")
    for m in re.finditer(r"\bportEND_SWITCHING_ISR\s*\(", text):
        add(line_of(text, m.start()), WARN,
            "portEND_SWITCHING_ISR 是其他移植层的写法：ESP32 惯用 portYIELD_FROM_ISR(woken)")

    # ---- R7: 硬件等待循环必须带超时（任务上下文）----
    for m in re.finditer(r"\bwhile\s*\(", text):
        if in_spans(m.start(), isr_spans):
            continue
        op = m.end() - 1
        cp = match_paren(text, op)
        cond = text[op + 1: cp]
        if re.fullmatch(r"\s*(1|0|!0|true)\s*", cond):
            continue  # 主循环 while(1) 属正常设计
        if not re.search(r"\w+\s*\(", cond):
            continue  # 条件不含函数调用（如 while(!done)）交给人判断，弱提示
        j = cp + 1
        while j < len(text) and text[j].isspace():
            j += 1
        if j < len(text) and text[j] == "{":
            body = text[j: match_brace(text, j) + 1]
        else:
            se = text.find(";", j)
            body = text[j: se + 1] if se != -1 else ""
        timeout_evidence = ("--" in cond + body or "-=" in cond + body
                            or "esp_timer_get_time" in cond + body
                            or "vTaskDelay" in body or "timeout" in cond.lower())
        if not timeout_evidence:
            add(line_of(text, m.start()), WARN,
                "硬件等待循环未见超时退出：每个等待必须有超时与失败分支"
                "（esp_timer_get_time 界限 / i2c xfer_timeout_ms / uart timeout_ms）")

    # ---- R8: 任务代码动态内存（ESP32 允许初始化期分配；ISR/周期路径禁止）----
    for f in funcs:
        if f["name"] in isr_names:
            continue  # ISR 内已按 VIOLATION 报过
        if f["name"] in task_cbs:
            continue  # 回调内在下面 B 规则报
        for hm in ISR_HEAP_RE.finditer(f["body"]):
            add(line_of(text, f["open"] + 1 + hm.start()), WARN,
                f"'{f['name']}' 内使用动态内存 '{hm.group(1)}()'：只允许初始化期一次性分配；"
                "周期路径/DMA 缓冲必须静态或 heap_caps_malloc 指定 caps")

    # ---- R9: 任务栈深度（单位是字节！STM32 words 惯性高危）----
    for m in re.finditer(r"\bxTaskCreate(?:PinnedToCore)?\s*\(", text):
        op = m.end() - 1
        cp = match_paren(text, op)
        args = split_top_args(text[op + 1: cp])
        if len(args) < 3:
            continue
        stack_txt = args[2].strip()
        num = re.fullmatch(r"(\d+)U?L?", stack_txt)
        line = line_of(text, m.start())
        if num:
            n = int(num.group(1))
            if n < 512:
                add(line, VIOL,
                    f"xTaskCreate* 栈深度 {n}：ESP32 栈单位是字节（STM32 是字，迁移惯性会溢出）——"
                    "最小 2048 字节起步，printf/ESP_LOG 路径 3072+")
            elif n < 2048:
                add(line, WARN,
                    f"xTaskCreate* 栈深度 {n} 字节偏小：建议 2048 起步；"
                    "交付前用 uxTaskGetStackHighWaterMark 复核并说明")

    # ---- R10: NVS 先于 WiFi（工程级）----
    for m in re.finditer(r"\besp_wifi_init\s*\(", text):
        if not project["has_nvs_init"]:
            add(line_of(text, m.start()), VIOL,
                "调用 esp_wifi_init 但全工程未见 nvs_flash_init()：WiFi 的校准/配置数据存 NVS，"
                "必须先初始化（含 NO_FREE_PAGES erase→retry 范式，见 peripheral-recipes.md §9）")
    # NVS 写后 commit
    if re.search(r"\bnvs_set_\w+\s*\(", text) and not re.search(r"\bnvs_commit\s*\(", text):
        add(1, WARN, "本文件有 nvs_set_* 写入但未见 nvs_commit()：NVS 写必须 commit 才落盘")

    # ---- R11: Arduino 轨专项 ----
    for m in re.finditer(r"\bICACHE_RAM_ATTR\b", text):
        add(line_of(text, m.start()), VIOL,
            "ICACHE_RAM_ATTR 是废弃写法（IDF 亦无此宏）：改用 IRAM_ATTR")
    is_arduino = path.suffix == ".ino" or any(f["name"] in ("setup", "loop") for f in funcs)
    if is_arduino:
        loop_fn = next((f for f in funcs if f["name"] == "loop"), None)
        if loop_fn:
            if re.search(r"\bwhile\s*\(\s*(1|true)\s*\)|\bfor\s*\(\s*;;\s*\)", loop_fn["body"]):
                add(line_of(text, loop_fn["start"]), VIOL,
                    "loop() 内出现 while(1)/for(;;)：loop() 本身就是循环体，内层死循环会饿死 "
                    "IDLE 触发 Task WDT；长忙等至少要 delay(1)/yield() 让出")
            has_block_call = bool(re.search(r"\bwhile\s*\(", loop_fn["body"])) and \
                not ARDUINO_BAN_CALL_RE.search(loop_fn["body"])
            if has_block_call:
                add(line_of(text, loop_fn["start"]), WARN,
                    "loop() 有 while 轮询但未见 delay/yield/vTaskDelay：必须让出，"
                    "防 loopTask 触发看门狗")
        if re.search(r"\bledcSetup\s*\(|\bledcAttachPin\s*\(", text):
            add(1, WARN,
                "检测到 ledcSetup/ledcAttachPin（core 2.x API）：arduino-esp32 3.x 已改为 "
                "ledcAttach(pin,freq,res)+ledcWrite(pin,duty)，按已装 core 大版本核对"
                "（见 references/arduino-track.md 迁移表）")

    # ---- 铁律 B: 任务上下文回调禁阻塞 ----
    for f in cb_funcs:
        for bm in TASKCB_BLOCK_RE.finditer(f["body"]):
            add(line_of(text, f["open"] + 1 + bm.start()), VIOL,
                f"回调 '{f['name']}'（esp_timer/esp_event/ESP-NOW 等任务上下文）内阻塞 "
                f"'{bm.group(1)}()'：回调只做短处理，长活置标志/发通知转任务处理")
        for hm in ISR_HEAP_RE.finditer(f["body"]):
            add(line_of(text, f["open"] + 1 + hm.start()), VIOL,
                f"回调 '{f['name']}' 内使用动态内存：回调路径禁止堆操作")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="ESP32 生成代码工程纪律检查（启发式）")
    ap.add_argument("files", nargs="*", help="要检查的 .c/.ino/.cpp 文件（多文件工程请一起传入）")
    ap.add_argument("--dir", help="递归检查该目录下所有 .c/.ino/.cpp")
    args = ap.parse_args(argv)

    exts = (".c", ".ino", ".cpp")
    paths = [Path(p) for p in args.files]
    if args.dir:
        paths.extend(sorted(p for p in Path(args.dir).rglob("*") if p.suffix in exts))
    if not paths:
        ap.error("请提供至少一个 .c/.ino 文件或 --dir 目录")

    SKIP_DIR_PARTS = ("build", "managed_components", ".pio", "third_party",
                      "middlewares", "libraries", "dependencies")
    to_check = []
    skipped = 0
    for p in paths:
        if args.dir and any(part.lower() in SKIP_DIR_PARTS for part in p.parts):
            skipped += 1
            continue
        if not p.is_file():
            continue
        to_check.append(p)
    if not to_check:
        print("结果: 无可检查文件")
        return 2

    texts = {}
    for p in to_check:
        try:
            texts[p] = neutralize(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            findings_pre = (str(p), 0, WARN, f"无法读取：{exc}")
            texts[p] = ""
        else:
            findings_pre = None

    # 工程级事实：NVS 初始化是否存在于任意被检查文件
    combined = "\n".join(texts.values())
    project = {
        "has_nvs_init": bool(re.search(r"\bnvs_flash_init\s*\(", combined)),
        "flags": set(re.findall(r"\bESP_INTR_FLAG_\w+", combined)),
    }

    findings = []
    if findings_pre:
        findings.append(findings_pre)
    irq_owner = {}
    checked = 0
    for p, text in texts.items():
        checked += 1
        analyze(p, text, findings, irq_owner, project)

    by_file = {}
    for f, line, level, msg in findings:
        by_file.setdefault(f, []).append((line, level, msg))
    for f in sorted(by_file):
        print(f"[{f}]")
        for line, level, msg in sorted(by_file[f]):
            print(f"  行{line:<5} [{level}] {msg}")
    n_v = sum(1 for x in findings if x[2] == VIOL)
    n_w = sum(1 for x in findings if x[2] == WARN)
    print(f"-- 检查文件: {checked}  违规(VIOLATION): {n_v}  警告(WARNING): {n_w} --")
    if skipped:
        print(f"-- 已跳过厂商/产物目录文件: {skipped}（不参与纪律检查）--")
    if checked == 0:
        print("结果: 无可检查文件")
        return 2
    if n_v:
        print("结果: FAIL —— 存在 VIOLATION，全部修复后才能交付")
        return 1
    print("结果: PASS —— 无 VIOLATION（WARNING 需逐条给出接受理由）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
