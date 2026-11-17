# evals — 技能静态测试（不依赖在线评分服务）

四份任务书测同一件事：**拿到任务书的 agent（装了本技能）能否按 SKILL.md 的流程产出
纪律合格、坑位不踩的代码**。运行方式刻意保持静态：

1. 新开会话（或子代理），只给它任务书路径 + 源仓库可读权限；
2. 产出到临时目录后，对照任务书内的「行为清单」逐条核对，再跑
   `python scripts/validate_esp_generated.py --dir <输出目录>`（期望 0 VIOL）；
3. 「必查规则」列给出该任务最容易踩的坑位编号（known-pitfalls.md），
   命中任一即记失败并回写教训。

| 任务书 | 覆盖域 | 最易踩 |
| --- | --- | --- |
| wifi-reconnect-nvs.md | STA 事件循环、NVS 参数、重连退避 | #78/#80/#88 段、R10 |
| ble-hid-keyboard.md | NimBLE、HID 描述符、notify | #36–53 段、R1 |
| lowpower-sensor.md | 深睡、RTC 定时、ADC 均值 | 低功耗文档 §、R8 |
| rs485-modbus-poll.md | UART RS485 模式、CRC、轮询超时 | #116–124 段、R13 |

评分不自动化（克制清单：不引在线服务）；每次人工评测后在 ROADMAP.md 记一行结果。
任务书措辞即用户原话风格——不给提示词以外的信息。
