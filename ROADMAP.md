# ROADMAP — easyesp 沉淀进度

> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）。

## 已沉淀（本轮，全部文档对齐官方文档、未上板实测）

| 项 | 文件 | 状态 |
|---|---|---|
| 主文件（路由/工作流/硬约束/自检/资源表） | `SKILL.md` | 完成 |
| IDF 工程基础与构建闭环 | `references/esp-idf-basics.md` | 完成 |
| Arduino 轨（arduino-esp32 3.x） | `references/arduino-track.md` | 完成 |
| 芯片差异（esp32/S3/C3） | `references/chip-family-notes.md` | 完成 |
| 引脚禁区与默认脚 | `references/gpio-pinout-guide.md` | 完成 |
| 中断与并发纪律 | `references/isr-and-concurrency-rules.md` | 完成 |
| FreeRTOS 任务/内存/TWDT | `references/freertos-on-esp32.md` | 完成 |
| 外设配方（GPIO/UART/I2C/SPI/LEDC/ADC/NVS/gptimer/WS2812） | `references/peripheral-recipes.md` | 完成 |
| WiFi 全栈（STA/AP/ESP-NOW/MQTT/HTTP/OTA） | `references/wifi-networking.md` | 完成 |
| 低功耗与深睡 | `references/power-and-sleep.md` | 完成 |
| 症状速查（Guru Meditation/addr2line/WDT） | `references/symptom-quickref.md` | 完成 |
| 坑清单 35 条 | `references/known-pitfalls.md` | 完成 |
| 模板 ×3 | `templates/main_idf.c` / `main_arduino.ino` / `sdkconfig.defaults` | 完成 |
| 纪律检查器 | `scripts/validate_esp_generated.py` | 完成（反例 16 VIOLATION / 模板 0 违规自测通过） |
| 示例工程 | `examples/blink_uart_demo/` | 完成（未上板） |
| 反例样本 | `tests/bad_sample_isr.c` / `bad_sample_task.c` | 完成 |

## 待验证（首个实测工程时逐项确认并回写）

- [ ] `idf.py build` 编译通过（模板/示例）：IDF 5.3.1 实际编译暴露的 API 拼写与头文件问题
- [ ] IRAM_ATTR ISR 与 flash 写（NVS）交叉运行不 crash
- [ ] I2C 新驱动（`i2c_master.h`）在目标芯片上的实际行为与超时参数
- [ ] ADC oneshot + 校准（line fitting）实测值
- [ ] gptimer on_alarm 回调上下文（默认中断上下文 vs dispatch 方法）验证
- [ ] ESP-NOW 对端兼容（经典 vs S3 vs C3 混连）
- [ ] 深睡电流与唤醒源实测（timer/EXT0/EXT1/touch/gpio）
- [ ] Arduino 3.x LEDC/analogWrite 在已装 core 上的实际行为
- [ ] validator 规则在真实工程上的误报率评估

## 下一批候选主题

- BLE/NimBLE 从机与主机示例
- 以太网（LAN8720/IP101）与 Wi-Fi 共存
- USB Host / USB Serial JTAG 进阶
- esp32-camera 图像采集
- ULP RISC-V 协处理器
- ESP32-C6 / H2 / P4（Wi-Fi 6 / 双模）扩展
- ESP-IDF 6.x 迁移指南（如发布）
- OTA 双分区进阶（回滚/差分）与安全启动
- Zigbee / Thread（802.15.4 芯片）
- 量产测试（RF 校准、efuse）

## 沉淀机制

1. 使用中发现新坑/新配方 → 征得用户同意后写回对应 `references/` 文档（保持"何时读/状态"头部两行）。
2. 改进检查规则 → 更新 `validate_esp_generated.py` 并跑反例自测（`tests/`）确认无回归。
3. 实测完成 → 更新 `SKILL.md` 头部实测状态声明与本表"待验证"清单，记录芯片型号与工程类型。
