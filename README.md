# easyesp — ESP32 嵌入式开发辅助技能（DSH Skill）

面向 AI agent 的 ESP32 固件开发知识技能：**双轨框架**（ESP-IDF 5.3.x 主轨 + Arduino arduino-esp32 3.x 副轨）、**三芯片覆盖**（经典 ESP32 / ESP32-S3 / ESP32-C3），带工程纪律检查器与沉淀机制。
对标同作者的 STM32 技能（embed），把"能生成代码"升级为"能按老手纪律生成代码并静态自检"。

> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）。
> 每次生成都应声明"未经编译与上板验证"，并给出验证路径（idf.py build → flash → monitor）。

## 目录结构

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 技能主文件：模式路由、六步工作流、11 条硬约束、自检清单、资源表（agent 的入口） |
| `references/` | 14 份知识文档：IDF 基础、芯片差异、引脚禁区、ISR 并发、FreeRTOS、外设配方、WiFi/网络、Arduino 轨、BLE HID 键盘、实时控制（飞控）、IoT 网关、低功耗、症状速查、53 条坑清单 |
| `templates/` | `main_idf.c`（IDF 骨架）、`main_arduino.ino`（Arduino 骨架）、`sdkconfig.defaults`（配置基线） |
| `scripts/validate_esp_generated.py` | 纪律检查器：IRAM_ATTR/FromISR/临界区方向/栈字节/NVS-before-WiFi/BLE API 入 ISR/BLE 回调阻塞/Arduino loop 等规则，`VIOLATION` 清零才交付 |
| `examples/blink_uart_demo/` | 完整可编译的最小 IDF 工程示例（点灯 + 日志，未上板） |
| `tests/bad_sample*.c*` | 故意违规的反例样本（含 BLE 反例/正例 `.cpp`），用于检查器自测 |
| `ROADMAP.md` | 沉淀进度与下一批主题 |

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

## 本机环境注记

- ESP-IDF 5.3.1 实际目录 `D:\ESPIDE\Espressif\frameworks\esp-idf-v5.3.1`；激活脚本 `D:\ESPIDE\Espressif\idf_cmd_init.bat`（桌面有快捷方式）。
- 系统 `python` 是 Microsoft Store 空壳不可用；跑脚本用 IDF 自带解释器 `D:\ESPIDE\Espressif\python_env\idf5.3_py3.11_env\Scripts\python.exe` 或激活 IDF 后的 `python`。
- 检查器只用 Python 标准库（argparse/re/pathlib），无需额外依赖。
- 本机 Arduino15 目录装有 arduino-esp32 core **2.0.11**（含经典 BLE 库，位于 `libraries\BLE`）；BLE HID 文档按 2.x/3.x 双版本标注，本机实测以 2.0.11 为准。

## 维护

发现 API 写法有误、新配方、新坑、检查规则改进时：**征得用户同意后**更新对应文件并记入 [ROADMAP.md](ROADMAP.md)。首个实测工程（编译→烧录→上板）完成后，把实测修正写回文档、更新状态声明。

## 参考

- ESP-IDF 编程指南：<https://docs.espressif.com/projects/esp-idf/zh_CN/v5.3/esp32/>
- arduino-esp32（3.x）：<https://docs.espressif.com/projects/arduino-esp32/en/latest/>
- ESP32 技术参考手册与 datasheet（芯片差异与引脚事实来源）

## License

MIT，见 [LICENSE](LICENSE)。
