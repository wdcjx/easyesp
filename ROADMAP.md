# ROADMAP — easyesp 沉淀进度

> 状态：文档对齐沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档；含《ESP32 软件开发避坑手册（量产级）》文档沉淀）**＋** 实战工程沉淀（BLE HID / 实时控制 / IoT 网关 / 语音 AI 助手（xiaozhi） / MAX30102 心率血氧 / 电机控制与 CAN（FOC 轮腿） / Mind+ 教育机器人（瑞龙 ESP32-E） / MicroPython 商用环境控制器（env-controller） / RS-485 Modbus RTU 主机（tiny485-mbrtu） / BLE+微信小程序外设（cw_esp32_ble_weapp） / POV 裸眼 3D 风扇屏（3-d-bare-eye-fan-screen） / ESP32-CAM 双机智能小车（stm32-car-project） / Wi-Fi NAT 中继路由（esp32s3-wifi-relay）十三份文档与坑清单 #36–81、#94–173，源自已上板运行的源工程，转写未二次复测）。

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

## 已沉淀（第六轮：量产避坑手册提炼）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| 量产工程纪律 | `references/production-readiness.md` | 源自用户提供的《ESP32 软件开发避坑手册（量产级）》docx 转写提炼（文档沉淀，未上板）：内存泄漏与碎片/栈水位/弱网限流/OTA 量产铁律/低功耗分层/量产前检查清单 12 项 |
| 坑清单量产手册类 82–93 | `references/known-pitfalls.md` | 内存碎片最大块不足/IRAM 塞爆/栈水位无监测/递归爆栈/假连接/弱网猛发/NVS 频写/PHY 校准缺失/RC 漂移/OTA 断点续传/量产日志/OTA 互斥，共 12 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（量产/上线/交付/检查清单/内存泄漏/碎片/断点续传）、计数 81→93、README 18 份；README 标题去「（DSH Skill）」括号（技能可给任意 agent 调用） |

## 已沉淀（第七轮：Mind+ 教育机器人扩展库）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| Mind+ 教育机器人扩展 | `references/mindplus-robot-ext.md` | 源自瑞龙制造 ESP32 物联网机器人 Mind+ 用户扩展库 V0.0.2（已上板，含 fireBeetleEsp32E 编译产物实证；MIT）：Mind+ 扩展库结构（config.json/main.ts 生成器/_menus/.mpext=ZIP/.mp 内嵌库）、MCPWM 电机 H 桥（unit×timer 映射+符号-幅值换向）、PCNT 正交编码器（ESP32Encoder 三模式）、FPV 遥控器 UART 协议（0x66…0x99 帧）、I2C 计分器（0x51/0x20）、RL_PID、legacy→IDF 5.2+ 新 API 迁移注记 |
| 坑清单教育机器人类 94–101 | `references/known-pitfalls.md` | MCPWM 50Hz 频率 bug/零速双高刹车语义/FpvReadByte 越界 UB/校验和优先级/FPV 脉冲窗丢命令/.mp 内嵌旧库版本漂移（V0.0.1 缺 bit4/bit7 实证）/生成器同键覆盖/legacy API 弃用线，共 8 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（Mind+/图形化编程/MCPWM/PCNT/编码器/H 桥/FPV/瑞龙）、计数 93→101、README 19 份、实战文档 6→7 份 |

## 已沉淀（第八轮：MicroPython 商用环境控制器）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| MicroPython 商用工程范式 | `references/micropython-env-controller.md` | 源自 env-controller v1.5.1-beta（已上板商用部署；ESP32-S3 N16R8，自编译 MicroPython v1.28，16MB flash+8MB PSRAM）：asyncio 10 服务化骨架（SERVICES+create_task+done_callback）、main.py 别名技巧、GC threshold 小步策略、IOQueue monkey-patch、配置驱动 Modbus 主站（指令-通道 schema/符号扩展纪律/UART 自愈）、RTU 从站+TCP 防冻（单任务非阻塞 socket）、自写 MQTT 3.1.1（umqtt bug 规避）、HA Discovery 生命周期（ha_disc.json diff+空 retain）、涂鸦 TuyaLink 直连（HMAC 一机一密/物模型缓存）、规则引擎（滞回/边沿/稳定 id）、配置三轨（NVS/flash JSON/engineer 白名单）、防变砖 OTA（tar 校验链+.mpy v6 绑定+回滚）、W5500 全链路 C 下沉（_spi_keep 防 GC）、C_MIGRATION 结论（渐进下沉不全迁） |
| 坑清单 MicroPython 商用类 102–115 | `references/known-pitfalls.md` | microdot body 上限/IOQueue 崩事件循环/大 GC 停顿/SPI 被 GC 析构/RS485 DE 时序/帧空闲判定/写回显误判/Modbus-TCP 连断风暴冻结/u16 符号扩展/asyncio.sleep 单例被吞/import main 重执行/.py 优先 .mpy/MQTT 认证+假死/OTA 变砖链，共 14 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（MicroPython/mpy/Modbus/RS485/Tuya/涂鸦/Home Assistant/规则引擎/asyncio）、计数 101→115、README 20 份、实战文档 7→8 份；双轨之外补 MicroPython 第三轨范式 |

## 已沉淀（第九轮：RS-485 Modbus RTU 主机库）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| RS-485 与 Modbus RTU 主机 | `references/modbus-rtu-485.md` | 源自 tiny485-mbrtu v1.0（ZeroOneLab/MIT，STM32F103ZE+MAX485 已上板；ESP32 移植段为文档新写未编译）：三层架构与 6 函数移植面、RTU 协议事实速查表（帧/CRC16 0xA001 低在前/功能码/异常码/T3.5/T1.5/8E1 规范 vs 8N1 事实）、核心层精读（crc16 位算法/溢出整包丢弃/无符号回绕安全）、ESP-IDF 双方案（UART_MODE_RS485_HALF_DUPLEX 硬件方向 vs 手动 DE+uart_wait_tx_done 铁律）、事件队列任务替代中断回调、wait_data 改造版（字节间隔判帧完+vTaskDelay）、Arduino 轨（flush 语义）、与 env-controller 取舍表、可复用模式 7 条 |
| 坑清单 Modbus 主机类 116–124 | `references/known-pitfalls.md` | 忙等烧满超时+无 yield/64B 缓冲溢出伪装 TIMEOUT（README"≤123"与规范 125 不符）/ERR_PARAM 从不返回/lun 越界写/DE 拉低截尾（write_bytes 仅入队）/溢出后半帧当新帧/广播写误报超时/DE与RE 接法决定回显/DE 建立延时写死 1ms，共 9 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（485/CRC16/变频器）、计数 115→124、README 21 份、实战文档 8→9 份 |

## 已沉淀（第十轮：BLE + 微信小程序外设）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| BLE+小程序外设实战 | `references/ble-weapp-morse-trainer.md` | 源自 cw_esp32_ble_weapp v0.0.3（作者已上板多年，B 站三视频演示；本文为源码转写未二次复测）：瘦设备+胖网关分层（ESP32 零 WiFi/MQTT，小程序持云端）、小程序蓝牙 API 链与 iOS/Android deviceId 差异、GATT 单特征四属性命令管道（含冒号分割器越界写栈实证 bug）、Bluedroid 骨架+断连重广播修复版、CW 时序参数体系与两次空格状态机、地狱模式容错窗公式、touchRead 触摸键（经典专属，S3/C3 无）、EEPROM 定长记录+magic 首启 vs Preferences、core 3.x ledc/NimBLE 迁移线 |
| 坑清单 BLE 小程序外设类 125–138 | `references/known-pitfalls.md` | 断连不重启广播永久失联/onWrite 内阻塞播放卡 BLE 栈/手动键上拉靠自动键副作用/GPIO0 strapping 做按键/touchRead 偶发 0（二次读防御）/共享全局 String 无锁/ble_send 声明定义签名漂移/每参数一次 EEPROM 全量 commit/定长 5 字符截断/play_code 变量错位（s_split_time 失效）/分割器越界写栈/自捶 delay 阻塞无 iambic/setMinPreferred 后者覆盖/String 码表堆碎片，共 14 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（微信小程序/weapp/GATT/CW/莫尔斯/电键/触摸键/蜂鸣器）、计数 124→138、README 22 份、实战文档 9→10 份、symptom-quickref §9.9（125–138） |

## 已沉淀（第十一轮：POV 裸眼 3D 风扇屏）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| POV 风扇屏实战 | `references/pov-fan-display.md` | 源自 3-d-bare-eye-fan-screen v1.0（2023，GPL-3.0，ESP32-S3 N16R8+TMC2209+WS2812×4 臂+MAX98357，作者已上板，B 站 BV1tN411y7ZS；本文为源码转写未二次复测）：POV 极坐标映射数据模型（200 角/圈×80 半径×4 臂 90° 偏移）/步进开环同步（100kHz 定时器 ISR 直写 GPIO 寄存器+num%speed 分频+每 8 脉冲进角）/软起动 0.9^N 斜坡防失步/WS2812 四通道 RMT/vendored led_strip 魔改非阻塞 refresh/tjpgd ROM 流式解码（含整数除法亮度缩放恒 0 实证 bug）/视频 OpenCV 离线预解为极坐标帧文件/MQTT topic 表与**大载荷分块陷阱**（1024B buffer 分块交付被逐块覆盖写）/HTTP 8080 路径穿越+CORS\*/三处明文账密/IDF 4.4.4→5.3 迁移表（legacy i2s/rmt/timer/事件循环） |
| 坑清单 POV 风扇屏类 139–153 | `references/known-pitfalls.md` | C 整数除法亮度缩放恒 0（PC float 语义漂移）/空文件系统裸 fopen 首启崩/feof 先判后读多计一帧/MQTT 分块覆盖写大文件必坏/publish 超 out_buffer 静默丢/路径穿越+CORS\* 无认证/公网明文账密三处泄露/100kHz ISR 非幂二模除/上下拉同开/BGR-RGB 换序/000%d 文件名漂移/固定尺寸缓冲越界/44100+44 头写死/455KB EMBED 死资源/魔改组件全局 tick 共享，共 15 条 |
| 收口更新 | `SKILL.md` / `README.md` / `ROADMAP.md` | 资源表+1 行、frontmatter 触发词（POV/视觉暂留/风扇屏/全息风扇/WS2812/灯带/步进电机/TMC2209）、计数 138→153、README 23 份、实战文档 10→11 份、symptom-quickref §9.10（139–153） |

## 已沉淀（第十二轮：工程化加固，源自 XRobot PkgKit 评估）

| 项 | 文件 | 来源与状态 |
|---|---|---|
| 真实编译 CI | `.github/workflows/build.yml` | IDF job：espressif/idf:v5.3.1 容器 idf.py build（esp32/S3/C3 三目标 × blink_uart_demo）；Arduino job：arduino-cli 1.5.1 + esp32 core 3.3.12 双锁版本三块板编译 arduino_blink_uart；月度 cron 检测上游漂移（XRobot PkgKit 的 CI 手法移植，弃其浮动 tag 反例） |
| MANIFEST 引脚声明核对 | `scripts/validate_esp_generated.py` | 新增 M 系列规则：`/* === EASYESP MANIFEST V1 === */` C 注释声明块（target/pins）→ target 合法性、芯片 GPIO 存在性（esp32 上限 39 且 20/24/28-31 不存在；S3 上限 48、22-25 不引出；C3 上限 21、11-19 受限）、一脚一功能、实际用脚全入表；无声明块的文件跳过（向后兼容）。源自 XRobot manifest-in-header 思想的 C 轨移植 |
| 自测基线 7→10 样本 | `scripts/ci_check.py` + `tests/manifest_good_sample.c` / `tests/manifest_bad_sample.c` + `examples/arduino_blink_uart/` | MANIFEST 正例（C3 声明一致 → PASS V0W0）/反例（同脚双功能+超上限+未声明 → FAIL V2W1）；Arduino 最小 sketch 入正例基线 |
| R12/R13 检查规则 | `scripts/validate_esp_generated.py` + `tests/bad_sample_rs485.c` | R12 legacy 驱动 API 警告（i2c/mcpwm/pcnt/timer/rmt/adc 旧调用与旧 include，坑 #101 家族）；R13 RS-485 手动 DE 时序（uart_write_bytes 后未 uart_wait_tx_done 即拉低 DE → VIOLATION，坑 #120 截尾帧）；基线 10→11 样本（FAIL V1W1 精确命中），旧样本零回归 |
| 单一事实源纪律 | `templates/main_idf.c` + `SKILL.md` | 模板头部带 MANIFEST 声明块；工作流第 2 步明确"分配表落进代码头部声明块，检查器核对声明与代码一致" |

## 待验证（首个实测工程时逐项确认并回写）

- [x] `idf.py build` 编译通过（示例）：build.yml 首跑（commit 181be9a，2026-11-07）esp32/S3/C3 三目标全绿，Arduino 三板（core 3.3.12）全绿；模板暂不在 CI 编译范围，保留待验证
- [ ] IRAM_ATTR ISR 与 flash 写（NVS）交叉运行不 crash
- [ ] I2C 新驱动（`i2c_master.h`）在目标芯片上的实际行为与超时参数
- [ ] ADC oneshot + 校准（line fitting）实测值
- [ ] gptimer on_alarm 回调上下文（默认中断上下文 vs dispatch 方法）验证
- [ ] ESP-NOW 对端兼容（经典 vs S3 vs C3 混连）
- [ ] 深睡电流与唤醒源实测（timer/EXT0/EXT1/touch/gpio）
- [ ] Arduino 3.x LEDC/analogWrite 实际行为实测（3.3.12 已由 build.yml CI 编译验证示例级代码，运行行为未实测；本机 Arduino15 实装 2.0.11）
- [ ] validator 规则在真实工程上的误报率评估
- [ ] BLE HID：经典 BLE 2.x（本机 core 2.0.11）在 C3 上对 iOS/Android/Windows 三平台发报告实测；onDisconnect 重广播实测（源工程已上板验证核心行为，本条为跨平台复现）
- [ ] 实时控制：互补滤波/混控在真实 IMU（如 MPU6050）上的姿态收敛与电机响应实测（源工程已上板飞行验证，本条为跨 IMU 复现）
- [ ] IoT 网关：PubSubClient setBufferSize 与服务器真实吞吐实测；ArduinoJson v6→v7 迁移后编译验证（源工程已上板部署验证 2.x 路径，本条为吞吐复现与 v7 编译）
- [ ] 语音 AI：xiaozhi 构建命令（scripts/build.py）在 IDF release/v6.1 下本机复现编译（本机仅 5.3.1，源工程已上板运行，本条为跨 SDK 复现）
- [ ] MAX30102：MPY（÷8 量纲）与 SparkFun（18bit 原值）两固件阈值衔接实测（源工程已上板，本条为跨固件复现）
- [ ] 电机控制：TWAI bus-off 恢复补丁（recovery+start）在真实总线上验证；MPU6050 量程显式设置后 DMP 输出一致性（源工程已上板运行，本条为修复项复现）

## 已沉淀（第十三轮：ESP32-CAM 双机智能小车）

| 产物 | 说明 | 验证状态 |
|---|---|---|
| references/esp32cam-stm32-bridge.md | stm32-car-project 转写（第 24 份）：双机架构/AI-Thinker 引脚预算/esp_camera 初始化/伪 MJPEG/跨 MCU 协议/死代码实证 | 源工程已上板，转写未二次复测 |
| 坑清单 #154–165 | ESP32-CAM/双机协处理类 12 条（readStringUntil 超时/协议漂移/引脚互斥/共地/PB3 PB4 remap 等） | 源自已上板工程静态审查 |
| SKILL/README/quickref 收口 | 触发词+路由+能力边界（Arduino 轨摄像头已沉淀、IDF 轨深度定制仍缺）+全量映射 #1–165 | ci_check 全绿 |

## 已沉淀（第十四轮：MultiButton 按键输入状态机）

| 产物 | 说明 | 验证状态 |
|---|---|---|
| references/multibutton-input-fsm.md | MultiButton v1.1.1 库研读（第 25 份）：5 状态 8 事件精读/时序参数耦合/IDF+Arduino 集成配方/vendor vs 自写决策/注意事项 | 源码逐行精读，未上板；MIT 可直接 vendor |
| SKILL/README 收口 | 触发词（按键/单击/双击/长按/连击/状态机/MultiButton/防抖）+导航表+资源表+25 份计数 | ci_check 全绿 |

同轮评估舍弃：Awesome-Embedded（纯链接目录，无 ESP32 特异性、非 agent 可直接执行的知识，链接时效差）。

## 已沉淀（第十五轮：Wi-Fi NAT 中继路由 + 补挖指令）

| 产物 | 说明 | 验证状态 |
|---|---|---|
| references/wifi-nat-relay.md | esp32s3-wifi-relay 转写（第 26 份）：APSTA+NAT 两调用/sdkconfig 最小集/信道跟随/README↔代码偏差实证（特性清单来自 martin-ger 上游） | 源工程已上板，转写未二次复测 |
| 坑清单 #166–173 | Wi-Fi NAT 中继类 8 条（证据链污染/真实密码入库/NAPT 漏配/默认接口/信道跟随/无限重连/空密码 OPEN/无 captive portal） | 源自已上板工程静态审查 |
| SKILL/README/quickref 收口 | 触发词（NAT/路由器/中继/APSTA/旅行路由）+路由+导航+资源表+全量映射 #1–173 | ci_check 全绿 |

同轮评估舍弃：esplay-retro-emulation（空 Gitee 模板仓库，仅脚手架 README 零代码）。
本轮起沉淀粒度升级：用户要求「补挖当时按模式压缩掉的具体细节」=转写保持细节级保真（帧协议/寄存器/时序具体事实，非模式级摘要）。

## 已沉淀（第十六轮：自更新指令）

| 产物 | 说明 | 验证状态 |
|---|---|---|
| SKILL.md「自更新」节 | 用户说「更新 easyesp」→ agent 定位技能目录（.claude/.dsh 依次探测）→ 三层更新：clone 形态 `git pull --ff-only` 带重试 / skills CLI 形态 `npx skills update`（原生，读 skills-lock.json）/ DSH 形态重新粘贴安装 → 读 ROADMAP 头部报告版本变化 | 纯指令文档，无代码 |
| README 安装节「更新」段 + 触发词 | 更新技能/自更新/检查更新/更新 easyesp | ci_check 全绿 |

## 下一批候选主题

- IDF 轨 BLE（NimBLE-IDF：GATT 自定义服务/主机扫描）——Arduino 轨 HID 已沉淀，本条只剩 IDF 轨
- 经典蓝牙 SPP 串口透传（Arduino）
- 以太网（LAN8720/IP101 RMII PHY）与 Wi-Fi 共存——W5500 SPI 以太网已由 micropython-env-controller §12 覆盖（商用上板），剩余 RMII PHY 与共存调度
- USB Host / USB Serial JTAG 进阶
- esp32-camera 图像采集（Arduino 轨 ESP32-CAM 已由 esp32cam-stm32-bridge 覆盖；剩余 IDF 轨驱动深度定制/多传感器）
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
