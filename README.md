# easyesp — ESP32 嵌入式开发辅助技能（DSH Skill）

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![ESP32](https://img.shields.io/badge/ESP32-S3%20%7C%20C3-blue)
![Tracks](https://img.shields.io/badge/ESP--IDF%20%C3%97%20Arduino-2%20tracks-informational)
[![CI](https://github.com/wdcjx/easyesp/actions/workflows/ci.yml/badge.svg)](https://github.com/wdcjx/easyesp/actions/workflows/ci.yml)
[![clones](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fwdcjx%2Feasyesp%2Fmain%2Fdocs%2Ftraffic.json&query=%24.clones.total&label=total%20clones&color=brightgreen)](https://github.com/wdcjx/easyesp/blob/main/docs/traffic_summary.md)
[![unique cloners](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fwdcjx%2Feasyesp%2Fmain%2Fdocs%2Ftraffic.json&query=%24.clones.uniques&label=unique%20cloners&color=blue)](https://github.com/wdcjx/easyesp/blob/main/docs/traffic_summary.md)

面向 AI agent 的 ESP32 固件开发知识技能：**双轨框架**（ESP-IDF 5.3.x 主轨 + Arduino arduino-esp32 3.x 副轨）、**三芯片覆盖**（经典 ESP32 / ESP32-S3 / ESP32-C3），带工程纪律检查器与沉淀机制。
对标同作者的 STM32 技能（[embed](https://github.com/wdcjx/Embedded-programming)），把"能生成代码"升级为"能按老手纪律生成代码并静态自检"。

> 状态：文档对齐沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）**＋** 实战工程沉淀（BLE HID / 实时控制 / IoT 网关 / 语音 AI 助手（xiaozhi） / MAX30102 心率血氧 / 电机控制与 CAN（FOC 轮腿）六份文档与坑清单 #36–81，源自已上板运行的源工程，转写未二次复测）。
> 每次生成都应声明"未经编译与上板验证"，并给出验证路径（idf.py build → flash → monitor）。

## 目录结构

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能主文件：模式路由、六步工作流、11 条硬约束、自检清单、资源表（agent 的入口） |
| `references/` | 17 份知识文档（逐份清单见下方） |
| `templates/` | `main_idf.c`（IDF 骨架）、`main_arduino.ino`（Arduino 骨架）、`sdkconfig.defaults`（配置基线） |
| `scripts/validate_esp_generated.py` | 纪律检查器：IRAM_ATTR/FromISR/临界区方向/栈字节/NVS-before-WiFi/BLE API 入 ISR/BLE 回调阻塞/Arduino loop 等规则，`VIOLATION` 清零才交付 |
| `scripts/ci_check.py` | CI 回归：validator 七样本判定基线 + 资源表/坑编号/文档计数一致性检查 |
| `examples/blink_uart_demo/` | 完整可编译的最小 IDF 工程示例（点灯 + 日志，未上板） |
| `tests/bad_sample*.c*` | 故意违规的反例样本（含 BLE 反例/正例 `.cpp`），用于检查器自测 |
| `.github/` | CI 工作流（ci.yml）、流量记录（traffic-record.yml）、Issue 模板（bug 反馈 / 知识沉淀建议） |
| `ROADMAP.md` | 沉淀进度与下一批主题 |
| `CONTRIBUTING.md` | 贡献指南：文档规范、validator 纪律、沉淀流程 |

<details>
<summary><b>references/ 全部 17 份文档</b>（点开清单）</summary>

| 文档 | 内容 |
|---|---|
| `esp-idf-basics.md` | IDF 工程闭环：目录/CMake 组件模型/idf.py 命令/menuconfig/分区表/日志 |
| `arduino-track.md` | Arduino 副轨：安装/库管理/与 IDF 的 API 映射/适用边界 |
| `chip-family-notes.md` | 三芯片差异：内核/外设/内存/USB/选型速查 |
| `gpio-pinout-guide.md` | 引脚分配：strapping 禁区/input-only/flash 占用/ADC 通道对照 |
| `isr-and-concurrency-rules.md` | 中断纪律：IRAM_ATTR/FromISR/临界区方向/volatile/队列 |
| `freertos-on-esp32.md` | FreeRTOS：任务/栈字节语义/优先级/核心绑定/看门狗 |
| `peripheral-recipes.md` | 外设配方：GPIO/UART/I2C/SPI/LEDC/ADC/NVS/gptimer/WS2812 |
| `wifi-networking.md` | Wi-Fi 全栈：STA/AP/事件机/ESP-NOW/MQTT/HTTP/OTA 回滚 |
| `ble-hid-arduino.md` | BLE HID 键盘：初始化序列/报告描述符/断连重广播/2.x-3.x 迁移 |
| `realtime-control.md` | 实时控制：节拍源/超级循环/IMU 校准/互补滤波/PID/混控/安全状态机 |
| `iot-gateway-patterns.md` | IoT 网关：多环境配置/PubSubClient 生产化/命令分发/掉电回放 |
| `voice-assistant-xiaozhi.md` | 语音 AI 助手（xiaozhi 转写）：安装构建/设备状态机/WebSocket 协议/AFE 音频管线/板级工厂/防变砖 OTA |
| `sensor-max30102.md` | MAX30102 心率血氧：接线/寄存器初始化序列/FIFO/AMPD 心率/R 比值 SpO2 |
| `motor-control-foc.md` | 电机控制与 CAN：TWAI 闭环/电压环协议/LQR 实时 K/VMC 雅可比/BLE 遥控载具 |
| `power-and-sleep.md` | 低功耗：深睡范式/唤醒源/RTC 内存/gpio_hold |
| `symptom-quickref.md` | 症状速查：Guru Meditation/WDT/复位原因/连接错误码 → 三步定位 |
| `known-pitfalls.md` | 81 条坑清单：供电/strapping/并发/网络/实战项目/传感器/语音 AI/电机控制，症状→根因→修法 |

</details>

## 安装（Windows）

本技能按 DSH skill 目录规范装配（`SKILL.md` + 同目录资源）。推荐用 junction 挂到本机技能目录，随仓库改动即时生效：

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\skills\easyesp" -Target "C:\Users\cjx20\Desktop\easyesp"
```

装好后在任意会话中提到 ESP32 / ESP-IDF / Arduino / WiFi / 点灯 等关键词即可自动触发，或直接点名 `easyesp`。

## 快速使用

- **生成代码**：描述需求（芯片模组、外设、框架），agent 走六步工作流产出完整工程代码。
- **纪律检查**：`python scripts/validate_esp_generated.py <文件...>` 或 `--dir <目录>`；退出码 0=通过、1=有 VIOLATION、2=用法错误。
- **故障排查**：贴 Guru Meditation / WDT / 复位日志，走 `references/symptom-quickref.md` 三步法。
- **检查器自测**：`python scripts/validate_esp_generated.py tests/bad_sample_isr.c tests/bad_sample_task.c tests/bad_sample_ble.cpp`（应 FAIL），再对 `templates/main_idf.c tests/good_sample_ble.cpp examples/blink_uart_demo/main/blink_uart_demo.c`（应 PASS）。
- **CI 全量回归**：`python scripts/ci_check.py`（validator 基线 + 一致性检查，与 GitHub Actions 相同）。

## 参与贡献

- 发现 API 写法有误、文档缺配方、新坑：欢迎开 [Issue](https://github.com/wdcjx/easyesp/issues)（模板二选一：bug 反馈 / 知识沉淀建议）或直接 PR，规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 有实测工程（编译→烧录→上板）的结论，尤其欢迎回写：把"未上板实测"状态推进为实测修正。

## 本机环境注记

- ESP-IDF 5.3.1 实际目录 `D:\ESPIDE\Espressif\frameworks\esp-idf-v5.3.1`；激活脚本 `D:\ESPIDE\Espressif\idf_cmd_init.bat`（桌面有快捷方式）。
- 系统 `python` 是 Microsoft Store 空壳不可用；跑脚本用 IDF 自带解释器 `D:\ESPIDE\Espressif\python_env\idf5.3_py3.11_env\Scripts\python.exe` 或激活 IDF 后的 `python`。
- 检查器只用 Python 标准库（argparse/re/pathlib/subprocess），无需额外依赖。
- 本机 Arduino15 目录装有 arduino-esp32 core **2.0.11**（含经典 BLE 库，位于 `libraries\BLE`）；BLE HID 文档按 2.x/3.x 双版本标注，本机实测以 2.0.11 为准。
- 本机沉淀的实战工程源码：`D:\ESP32project\`（xiaozhi-esp32-main、heart-rate-spo2-master、foc-wheel-legged-robot-master 等）。**xiaozhi-esp32 要求 ESP-IDF ≥6.0.1（推荐 release/v6.1 分支），本机 5.3.1 无法编译它**；其余工程以各 README 为准。

## 维护

发现 API 写法有误、新配方、新坑、检查规则改进时：**征得用户同意后**更新对应文件并记入 [ROADMAP.md](ROADMAP.md)。首个实测工程（编译→烧录→上板）完成后，把实测修正写回文档、更新状态声明。

## 参考

- ESP-IDF 编程指南：<https://docs.espressif.com/projects/esp-idf/zh_CN/v5.3/esp32/>
- arduino-esp32（3.x）：<https://docs.espressif.com/projects/arduino-esp32/en/latest/>
- ESP32 技术参考手册与 datasheet（芯片差异与引脚事实来源）

## License

MIT，见 [LICENSE](LICENSE)。
