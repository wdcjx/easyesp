# ROADMAP — easyesp 沉淀进度

> 状态：文档对齐沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）**＋** 实战工程沉淀（BLE HID / 实时控制 / IoT 网关 / 语音 AI 助手（xiaozhi） / MAX30102 心率血氧 / 电机控制与 CAN（FOC 轮腿）六份文档与坑清单 #36–81，源自已上板运行的源工程，转写未二次复测）。

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

## 已沉淀（第二轮：实战项目提炼，源自三个真实项目源码审计）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| BLE HID 键盘（Arduino 轨） | `references/ble-hid-arduino.md` | 源自 Keybrick（C3 BLE HID 键盘，**已上板量产运行**）；经典 BLE 2.x + NimBLE 双版本标注 |
| 实时控制（飞控/控制环） | `references/realtime-control.md` | 源自 Flix 四旋翼（github.com/okalachev/flix 注释版，**已上板飞行**）；IMU 校准/互补滤波/PID/混控/安全状态机 |
| IoT 网关模式 | `references/iot-gateway-patterns.md` | 源自 yihong-iot GatewayESP32Client（S3/Arduino/PubSubClient，**已上板部署**）；多环境配置/连接编排/发布防御/命令分发 |
| 坑清单实战章 36–53 | `references/known-pitfalls.md` | Keybrick 7 条 + Flix 7 条 + yihong 5 条，编号续接不改号 |
| 检查器 BLE 规则 | `scripts/validate_esp_generated.py` | R4 加 BLE API 入 ISR（VIOL）与 ->notify（WARN）；R13 加 setCallbacks/WiFi.onEvent/onConnect 类回调；REGISTRATION_RES 加 timerAttachInterrupt；FUNC_RE 兼容 C++ 类方法（缩进/override）。自测：新反例 5 VIOL/1 WARN、正例 0、旧基线 16/3 无回归 |
| BLE 测试样本 | `tests/bad_sample_ble.cpp` / `good_sample_ble.cpp` | 反例命中全部新规则；正例干净通过 |

## 已沉淀（第四轮：语音 AI 与传感器实战提炼）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| 语音 AI 助手范式 | `references/voice-assistant-xiaozhi.md` | 源自 xiaozhi-esp32（github.com/78/xiaozhi-esp32，**已上板运行**）：安装构建（IDF 6.x 门槛）/设备状态机/WebSocket+MQTT/UDP 协议/AFE 音频管线/板级工厂/防变砖 OTA |
| MAX30102 心率血氧 | `references/sensor-max30102.md` | 源自 heart-rate-spo2-master（Arduino+MicroPython+PC 三版，**已上板**）：寄存器初始化序列/FIFO 格式/AMPD 心率/R 比值 SpO2/量纲陷阱 |
| 坑清单传感器类 54–61 + 语音 AI 类 62–71 | `references/known-pitfalls.md` | MAX30102 8 条 + xiaozhi 10 条，编号续接不改号 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+2 行、frontmatter 触发词、计数 53→71、README 16 份、环境注记加 xiaozhi 路径与 IDF 6.x 要求 |

## 已沉淀（第五轮：电机控制实战提炼）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| 电机控制与 CAN（FOC 轮腿范式） | `references/motor-control-foc.md` | 源自 Skythinker foc-wheel-legged-robot（GPL-3.0，**已上板运行**）：TWAI 最小闭环+bus-off 补丁/电压环协议/LQR 实时 K 部署流/VMC 雅可比转置/BLE 遥控载具/分级失控保护 |
| 坑清单电机控制类 72–81 | `references/known-pitfalls.md` | CAN bus-off 静默/BLE 断连末指令/零偏硬编码/量程档不符/保护死等/跨任务无锁/低压假值/延迟叠加/调试帧裸写 RAM/上电黑窗，共 10 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（FOC/电机控制/CAN/TWAI/LQR/VMC/平衡车/轮腿/MPU6050）、计数 71→81、README 17 份 |

## 待验证（首个实测工程时逐项确认并回写）

- [ ] `idf.py build` 编译通过（模板/示例）：IDF 5.3.1 实际编译暴露的 API 拼写与头文件问题
- [ ] IRAM_ATTR ISR 与 flash 写（NVS）交叉运行不 crash
- [ ] I2C 新驱动（`i2c_master.h`）在目标芯片上的实际行为与超时参数
- [ ] ADC oneshot + 校准（line fitting）实测值
- [ ] gptimer on_alarm 回调上下文（默认中断上下文 vs dispatch 方法）验证
- [ ] ESP-NOW 对端兼容（经典 vs S3 vs C3 混连）
- [ ] 深睡电流与唤醒源实测（timer/EXT0/EXT1/touch/gpio）
- [ ] Arduino 3.x LEDC/analogWrite 在已装 core 上的实际行为（本机 Arduino15 实装 2.0.11，3.x 行为未实测）
- [ ] validator 规则在真实工程上的误报率评估
- [ ] BLE HID：经典 BLE 2.x（本机 core 2.0.11）在 C3 上对 iOS/Android/Windows 三平台发报告实测；onDisconnect 重广播实测（源工程已上板验证核心行为，本条为跨平台复现）
- [ ] 实时控制：互补滤波/混控在真实 IMU（如 MPU6050）上的姿态收敛与电机响应实测（源工程已上板飞行验证，本条为跨 IMU 复现）
- [ ] IoT 网关：PubSubClient setBufferSize 与服务器真实吞吐实测；ArduinoJson v6→v7 迁移后编译验证（源工程已上板部署验证 2.x 路径，本条为吞吐复现与 v7 编译）
- [ ] 语音 AI：xiaozhi 构建命令（scripts/build.py）在 IDF release/v6.1 下本机复现编译（本机仅 5.3.1，源工程已上板运行，本条为跨 SDK 复现）
- [ ] MAX30102：MPY（÷8 量纲）与 SparkFun（18bit 原值）两固件阈值衔接实测（源工程已上板，本条为跨固件复现）
- [ ] 电机控制：TWAI bus-off 恢复补丁（recovery+start）在真实总线上验证；MPU6050 量程显式设置后 DMP 输出一致性（源工程已上板运行，本条为修复项复现）

## 下一批候选主题

- IDF 轨 BLE（NimBLE-IDF：GATT 自定义服务/主机扫描）——Arduino 轨 HID 已沉淀，本条只剩 IDF 轨
- 经典蓝牙 SPP 串口透传（Arduino）
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
