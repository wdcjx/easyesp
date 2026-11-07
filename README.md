# easyesp — ESP32 嵌入式开发辅助技能

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![ESP32](https://img.shields.io/badge/ESP32-S3%20%7C%20C3-blue)
![Tracks](https://img.shields.io/badge/ESP--IDF%20%C3%97%20Arduino-2%20tracks-informational)
[![CI](https://github.com/wdcjx/easyesp/actions/workflows/ci.yml/badge.svg)](https://github.com/wdcjx/easyesp/actions/workflows/ci.yml)
[![clones](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fwdcjx%2Feasyesp%2Fmain%2Fdocs%2Ftraffic.json&query=%24.clones.total&label=total%20clones&color=brightgreen)](https://github.com/wdcjx/easyesp/blob/main/docs/traffic_summary.md)
[![unique cloners](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fwdcjx%2Feasyesp%2Fmain%2Fdocs%2Ftraffic.json&query=%24.clones.uniques&label=unique%20cloners&color=blue)](https://github.com/wdcjx/easyesp/blob/main/docs/traffic_summary.md)

面向 AI agent 的 ESP32 固件开发知识技能：**双轨框架**（ESP-IDF 5.3.x 主轨 + Arduino arduino-esp32 3.x 副轨）、**三芯片覆盖**（经典 ESP32 / ESP32-S3 / ESP32-C3），带工程纪律检查器与沉淀机制。
对标同作者的 STM32 技能（[embed](https://github.com/wdcjx/Embedded-programming)），把"能生成代码"升级为"能按老手纪律生成代码并静态自检"。

> 状态：文档对齐沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档；含《ESP32 软件开发避坑手册（量产级）》文档沉淀）**＋** 实战工程沉淀（BLE HID / 实时控制 / IoT 网关 / 语音 AI 助手（xiaozhi） / MAX30102 心率血氧 / 电机控制与 CAN（FOC 轮腿） / Mind+ 教育机器人（瑞龙 ESP32-E）七份文档与坑清单 #36–81、#94–101，源自已上板运行的源工程，转写未二次复测）。
> 每次生成都应声明"未经编译与上板验证"，并给出验证路径（idf.py build → flash → monitor）。

## 能力列表

**代码生成**

| 能力 | 说明 |
|---|---|
| 完整工程生成 | 按需求（芯片 / 模组 / 外设 / 框架）产出 main + CMakeLists + sdkconfig.defaults + 分区表的完整可编译工程 |
| 双轨框架 | ESP-IDF 5.3.x 主轨（idf.py 闭环 / 组件模型 / menuconfig / 分区表）；Arduino 副轨（库管理与 2.x→3.x 迁移） |
| 三芯片适配 | 经典 ESP32 / ESP32-S3 / ESP32-C3 内核外设差异 + 引脚禁区核对（strapping / input-only / flash 占用 / ADC 通道） |

**领域配方**（references 按场景路由）

| 领域 | 覆盖 |
|---|---|
| 外设 | GPIO / UART / I2C（新驱动）/ SPI / LEDC（PWM、舵机）/ ADC（校准）/ gptimer / NVS / WS2812 |
| 网络与云 | STA / AP 事件状态机 / ESP-NOW / MQTT / HTTP / OTA（双分区回滚防变砖） |
| BLE | HID 键盘与媒体键：初始化序列、报告描述符、断连重广播、经典 BLE 与 NimBLE 双库路径 |
| 实时控制 | 节拍源 / IMU 校准 / 互补滤波姿态 / PID / 四旋翼混控 / 解锁与失控安全状态机 |
| IoT 网关 | PubSubClient 生产化 / 多环境配置 / 命令信封分发 / 掉电回放 |
| 语音 AI | xiaozhi 范式：板级抽象工厂 / 设备状态机 / WebSocket 实时音频协议 / 防变砖 OTA |
| 传感器 | MAX30102 心率血氧：寄存器初始化序列 / FIFO 读取 / AMPD 找峰 / R 比值 SpO2 |
| 电机控制 | TWAI（CAN）最小闭环 / 电压环协议 / LQR 增益 / VMC 轮腿 / BLE 遥控载具 |
| 教育机器人 | Mind+ 图形化编程扩展库 / MCPWM 直流电机 H 桥 / PCNT 正交编码器 / FPV 遥控器 UART 协议 / I2C 计分器 |
| 低功耗 | 深睡三档 / 唤醒源 / RTC 内存 / gpio_hold |

**质量与排障**

| 能力 | 说明 |
|---|---|
| 静态纪律检查 | `validate_esp_generated.py` 13 类规则：IRAM_ATTR / FromISR / 临界区方向 / 栈字节 / NVS-before-WiFi / BLE API 入 ISR / 任务回调阻塞 / Arduino loop 纪律 |
| 101 条坑清单 | 症状→根因→修法 三列表格：供电 / strapping / 并发 / 网络 / 实战项目 / 传感器 / 语音 AI / 电机控制 / 量产手册 / 教育机器人 |
| 症状速查 | Guru Meditation 转储 / 看门狗 / 复位原因 / WiFi 断连码 → 三步定位法 |
| 量产就绪 | 内存泄漏与碎片 / 栈水位 / 弱网限流 / OTA 量产铁律 / 量产前 12 项检查清单 |

## 目录结构

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能主文件：模式路由、六步工作流、11 条硬约束、自检清单、资源表（agent 的入口） |
| `references/` | 19 份知识文档（逐份清单见下方） |
| `templates/` | `main_idf.c`（IDF 骨架）、`main_arduino.ino`（Arduino 骨架）、`sdkconfig.defaults`（配置基线） |
| `scripts/validate_esp_generated.py` | 纪律检查器：IRAM_ATTR/FromISR/临界区方向/栈字节/NVS-before-WiFi/BLE API 入 ISR/BLE 回调阻塞/Arduino loop 等规则，`VIOLATION` 清零才交付；纯 Python 标准库，无第三方依赖 |
| `scripts/ci_check.py` | CI 回归：validator 七样本判定基线 + 资源表/坑编号/文档计数一致性检查 |
| `examples/blink_uart_demo/` | 完整可编译的最小 IDF 工程示例（点灯 + 日志，未上板） |
| `tests/bad_sample*.c*` | 故意违规的反例样本（含 BLE 反例/正例 `.cpp`），用于检查器自测 |
| `.github/` | CI 工作流（ci.yml）、流量记录（traffic-record.yml）、Issue 模板（bug 反馈 / 知识沉淀建议） |
| `ROADMAP.md` | 沉淀进度与下一批主题 |
| `CONTRIBUTING.md` | 贡献指南：文档规范、validator 纪律、沉淀流程 |

<details>
<summary><b>references/ 全部 19 份文档</b>（点开清单）</summary>

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
| `mindplus-robot-ext.md` | Mind+ 教育机器人扩展：扩展库结构/MCPWM 电机 H 桥/PCNT 编码器/FPV 遥控 UART 协议/I2C 计分器 |
| `production-readiness.md` | 量产工程纪律：内存泄漏与碎片/栈水位/弱网限流/OTA 铁律/低功耗分层/量产前检查清单 |
| `power-and-sleep.md` | 低功耗：深睡范式/唤醒源/RTC 内存/gpio_hold |
| `symptom-quickref.md` | 症状速查：Guru Meditation/WDT/复位原因/连接错误码 → 三步定位 |
| `known-pitfalls.md` | 101 条坑清单：供电/strapping/并发/网络/实战项目/传感器/语音 AI/电机控制/量产手册/教育机器人，症状→根因→修法 |

</details>

## 安装

仓库地址：https://github.com/wdcjx/easyesp

**通用一键安装（Claude Code / Codex 等主流 Agent CLI）**：

```bash
npx skills add wdcjx/easyesp
```

该方式在同作者 embed 仓库已实测：自动识别技能名，完整带上 `references/`、`scripts/`（validator）、`templates/` 等子目录，并生成 `skills-lock.json` 便于团队复现。

**DeepSeek Harness (DSH)**：侧边栏「技能库」→ 粘贴仓库链接 https://github.com/wdcjx/easyesp 安装（自动克隆 + 热加载），或把整个 `easyesp` 文件夹放到 `~/.dsh/skills/easyesp`。

**手动**：`git clone https://github.com/wdcjx/easyesp.git`，把克隆出的文件夹改名为 `easyesp` 放到 `~/.claude/skills/`（或 `~/.dsh/skills/`）。

> 注意：安装时目录名应与 SKILL.md 中的 `name: easyesp` 一致。

**本机开发者（Windows，从本地检出即时生效）**：junction 挂载，仓库改动零拷贝同步：

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\skills\easyesp" -Target "<仓库检出路径>"
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

## 维护

发现 API 写法有误、新配方、新坑、检查规则改进时：**征得用户同意后**更新对应文件并记入 [ROADMAP.md](ROADMAP.md)。首个实测工程（编译→烧录→上板）完成后，把实测修正写回文档、更新状态声明。

## 参考

- ESP-IDF 编程指南：<https://docs.espressif.com/projects/esp-idf/zh_CN/v5.3/esp32/>
- arduino-esp32（3.x）：<https://docs.espressif.com/projects/arduino-esp32/en/latest/>
- ESP32 技术参考手册与 datasheet（芯片差异与引脚事实来源）

## License

MIT，见 [LICENSE](LICENSE)。
