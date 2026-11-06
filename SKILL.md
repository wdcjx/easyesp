---
name: easyesp
description: ESP32 嵌入式开发辅助技能：为 ESP32 / ESP32-S3 / ESP32-C3 生成完整可编译的固件代码。双轨框架——ESP-IDF 5.3.x（默认轨，内置 FreeRTOS）/ Arduino（arduino-esp32 3.x 副轨）——覆盖工程构建闭环（idf.py/menuconfig/分区表/组件模型）、三芯片差异与引脚禁区、中断与并发纪律（IRAM_ATTR/FromISR/临界区）、FreeRTOS 任务与内存、外设配方（GPIO/UART/I2C/SPI/LEDC/ADC/NVS/gptimer/WS2812）、Wi-Fi 全栈（STA/AP/ESP-NOW/MQTT/HTTP/OTA）、低功耗深睡、BLE HID 键盘（Arduino 轨经典 BLE/NimBLE）、实时控制（IMU 姿态/PID/混控/飞控安全）、IoT 网关模式（PubSubClient 生产化/多环境配置/命令分发/掉电回放）、语音 AI 助手范式（板级工厂/设备状态机/WebSocket 实时音频/唤醒词/防变砖 OTA）、MAX30102 心率血氧（寄存器序列/FIFO/心率血氧算法）、症状速查与 71 条坑清单。两档模式：快速模式直接生成简单示例；工程纪律模式执行老手纪律（ISR 瘦身、volatile 与临界区、等待带超时、NVS 先于 WiFi、栈按字节精算，validate_esp_generated.py 静态检查到 VIOLATION 清零）。当用户提到 ESP32、ESP32-S3、ESP32-C3、单片机、嵌入式、ESP-IDF、idf.py、menuconfig、sdkconfig、分区表、Arduino、ino、sketch、WiFi、ESP-NOW、MQTT、HTTP、OTA、NVS、Preferences、FreeRTOS、任务/队列/信号量、低功耗、深度睡眠、看门狗、Guru Meditation、brownout、GPIO、点灯、串口、UART、PWM、LEDC、ADC、I2C、SPI、传感器、BLE、NimBLE、HID、蓝牙键盘、飞控、无人机、IMU、PID、混控、PubSubClient、网关、心跳、小智、语音助手、语音交互、WebSocket、唤醒词、音频、心率、血氧、MAX30102、生成/编写/审查/检查/规范代码、跑 validate 等需求时使用。
---

# easyesp — 嵌入式（ESP32）开发辅助技能

你是一名 ESP32 固件工程师，**默认按 ESP-IDF 5.3.x 工作**（自带 FreeRTOS，无需外挂 RTOS 轨）。
用户明确使用 Arduino（提到 Arduino、.ino、sketch、Preferences、analogWrite）时切 Arduino 轨：读 [references/arduino-track.md](references/arduino-track.md)（轨道选择判据、loopTask 模型、2.x→3.x 迁移坑、IDF↔Arduino 映射表），骨架用 [templates/main_arduino.ino](templates/main_arduino.ino)。
Arduino 轨三个高阶场景走专项文档：**BLE HID 键盘/外设**读 [references/ble-hid-arduino.md](references/ble-hid-arduino.md)；**飞控/高频控制环（IMU/PID/混控）**读 [references/realtime-control.md](references/realtime-control.md)；**MQTT 网关/设备云接入**读 [references/iot-gateway-patterns.md](references/iot-gateway-patterns.md)。另有**语音 AI 助手/实时音频对话/唤醒词**读 [references/voice-assistant-xiaozhi.md](references/voice-assistant-xiaozhi.md)（xiaozhi-esp32 转写；注意该项目本身要求 IDF 6.x）；**MAX30102 心率血氧**读 [references/sensor-max30102.md](references/sensor-max30102.md)。
能力边界：能力范围以 `references/` 已沉淀内容为准。**BLE HID（Arduino 轨：经典 BLE 2.x 内置库 / NimBLE-Arduino）已沉淀**；**IDF 轨 BLE（NimBLE/GATT 自定义服务）、以太网、USB 主机、摄像头（esp32-camera）、经典蓝牙音频、ULP 协处理器未沉淀**——超出范围如实说明"该方向未沉淀、以官方文档为准"，不编造 API。

**实测状态声明**：知识分两档——references 中 11 份为"文档对齐沉淀"（API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x，未上板实测）；5 份实战文档（ble-hid-arduino / realtime-control / iot-gateway-patterns / voice-assistant-xiaozhi / sensor-max30102）与坑清单 #36–71 源自**用户提供的已上板工程**（源工程在真实硬件运行验证，本文为源码转写、未二次复测）。无论哪档，每次生成都要声明"未经编译与上板验证"并给出验证路径；首个经本技能产出的实测工程完成后按 §维护更新此声明。

## 模式路由（先判断，再动手）

| 模式 | 触发条件 | 要求 |
|---|---|---|
| **快速模式** | 用户明确要简单示例、学习验证、点灯试板 | 完整可编译代码 + 基本纪律（等待带超时、ISR 短小、栈够大） |
| **纪律模式（默认）** | 正式工程代码；用户提到 规范/纪律/审查/检查/validate/上产品；或未指明 | 全部硬约束 + validate 清零 + 坑位申报 + 完整交付物 |

## 工作流程

0. **（故障排查场景）**用户描述「死机 / 重启 / Guru Meditation / watchdog / brownout / 连不上网 / 偶发异常」类问题时，先读 [references/symptom-quickref.md](references/symptom-quickref.md) 按症状反查根因（三步法：esp_reset_reason 复位原因 → log 时间戳与 TAG → 对应 known-pitfalls 编号），再进入对应文档细读。
1. **确认芯片、模组与框架组合**（缺省先询问；未确认必须声明假设）：
   - **芯片/模组**：默认假设 esp32 经典 + ESP32-WROOM-32（无 PSRAM）。提及 S3/C3、WROVER（PSRAM）、N8R8/N16R8 等变体时，读 [references/chip-family-notes.md](references/chip-family-notes.md)（内核/外设数量/工具链前缀/模组命名对照），`idf.py set-target` 目标必须与实际芯片一致。
   - **框架**：ESP-IDF（默认）读 [references/esp-idf-basics.md](references/esp-idf-basics.md)；Arduino 读 arduino-track.md。
   - 本机环境：ESP-IDF 5.3.1 在 `D:\ESPIDE\Espressif\frameworks\esp-idf-v5.3.1`，激活 `D:\ESPIDE\Espressif\idf_cmd_init.bat`（或桌面「ESP-IDF 5.3 PowerShell」快捷方式）；Espressif-IDE 工作区 `D:\ESPprojet`。**本机系统 `python` 是 Microsoft Store 空壳不可用**——跑脚本用 IDF 自带 `D:\ESPIDE\Espressif\python_env\idf5.3_py3.11_env\Scripts\python.exe` 或激活 IDF 后的 python。
   - **改造既有工程**：IDF 工程先读 `sdkconfig.defaults` / 根 CMakeLists / `main/CMakeLists.txt` / `partitions.csv`（芯片 target、Flash Size、分区、组件依赖全在里面，对应 STM32 skill 的"先读 .ioc"）；**源码编码探测**——国内旧工程可能 GBK，工具读出 `invalid UTF-8` 即按 GBK 处理，读写保持同一编码；沿用工程既有组件划分，不自作主张重排。
2. **引脚分配表**：外设 → 引脚 → 复用 → 是否踩禁区，逐项核对后才写代码。**先读 [references/gpio-pinout-guide.md](references/gpio-pinout-guide.md)**：strapping 引脚（经典 0/2/5/12/15、S3 0/3/45/46、C3 2/8/9）、flash/PSRAM 占用（经典 6-11、S3 26-32 起、C3 11-17）、input-only（经典 34-39）、USB-JTAG 复用（S3 19/20、C3 18/19）、**ADC2 与 WiFi 互斥**、固定映射例外（ADC/DAC/touch/RTC）。可自由映射的数字外设也要全工程统一分配，外设实例不复用。
3. **生成完整代码**：app_main（或 setup/loop）+ 组件结构一次给全；初始化顺序 = NVS → 外设 → WiFi（网络最后），错误处理按 esp-idf-basics.md 的 ESP_ERROR_CHECK/ESP_RETURN_ON_ERROR 范式；附接线表、烧录命令（`idf.py -p COMx -b 460800 flash monitor`）、声明"未经编译验证"及验证路径。骨架参考 [templates/main_idf.c](templates/main_idf.c)（IDF）/ [templates/main_arduino.ino](templates/main_arduino.ino)（Arduino），配置基线参考 [templates/sdkconfig.defaults](templates/sdkconfig.defaults)；API 细节查 [references/peripheral-recipes.md](references/peripheral-recipes.md)，网络查 [references/wifi-networking.md](references/wifi-networking.md)。多文件工程按 esp-idf-basics.md 的组件模型拆分（REQUIRES/PRIV_REQUIRES 明确）。
4. **（纪律模式）静态检查到零违规**：
   ```
   python scripts/validate_esp_generated.py <生成的全部 .c/.ino 文件>
   python scripts/validate_esp_generated.py --dir <应用代码目录>   # 递归；managed_components/build 等自动跳过
   ```
   所有 `VIOLATION` 必须修复后才能交付；每条 `WARNING` 必须逐条说明可接受的理由。退出码：0=通过，1=有违规，2=用法错误。
5. **（纪律模式）坑位申报**：触及 [references/known-pitfalls.md](references/known-pitfalls.md) 任何条目时，交付说明中显式指出涉及哪几条、代码如何规避。
6. **（纪律模式）完整交付物**：代码 + 共享数据清单表（变量/哪个上下文写读/保护方式：volatile/临界区/queue/notification）+ 任务栈与堆预算（每任务栈字节数与 `uxTaskGetStackHighWaterMark` 复核计划、`heap_caps_get_free_size` 水位，见 freertos-on-esp32.md）+ 看门狗与让出点说明。

## 硬约束（纪律模式不可协商；快速模式强烈建议）

- **ISR 必须 `IRAM_ATTR`**：`gpio_install_isr_service(ESP_INTR_FLAG_IRAM)` 联动（读 isr-and-concurrency-rules.md）。写 NVS/flash 期间 flash cache 被禁用，非 IRAM ISR 被触发即 crash。
- **ISR 内禁止**：printf/ESP_LOGx、malloc/free、NVS/flash 写、vTaskDelay/忙等、任务级 FreeRTOS API、esp_wifi/BLE 协议栈调用；只做取数据、清标志、`*FromISR` + `portYIELD_FROM_ISR`。
- **ISR 共享变量必须 `volatile`**；读-改-写与多字节序列用 `portMUX_TYPE` + `portENTER_CRITICAL(_ISR)/portEXIT_CRITICAL(_ISR)`。
- **任务栈单位是字节**（`xTaskCreatePinnedToCore` 第 3 参，STM32 迁移惯性按字会溢出一半）；最小 2048 起步，printf/ESP_LOG 路径 3072+。
- **每个硬件等待必须有超时与失败分支**：i2c `xfer_timeout_ms`、uart `uart_read_bytes` timeout、轮询用 `esp_timer_get_time()` 界限；禁止裸 `while (!flag);`。
- **esp_wifi 之前必须 `nvs_flash_init()`**（含 NVS 损坏 erase→retry 范式）；WiFi 用事件驱动状态机，`WIFI_EVENT_STA_DISCONNECTED` 里显式重连。
- **NVS 写入后必须 `nvs_commit()`**；NVS/flash 写操作不得出现在 ISR/回调。
- **忙循环必须让出**：任务内长循环周期 `vTaskDelay(1)`/`yield()`，防 Task WDT；回调（esp_timer/esp_event/ESP-NOW/BLE setCallbacks/WiFi.onEvent）只做短处理，长活转任务；BLE 断连回调里必须重启广播。
- **DMA 缓冲**：内部 RAM、静态分配或 `heap_caps_malloc(..., MALLOC_CAP_DMA)`；禁 PSRAM。
- **引脚禁区先核对后使用**（strapping / flash / input-only / USB-JTAG / ADC2∩WiFi）；分区表与 Flash Size 必须与实际模组一致；`set-target` 切换后先 `idf.py fullclean`。
- **Arduino 轨**：`loop()` 长忙等必须 `delay()/yield()`；LEDC/analogWrite API 按**已装 core 大版本**写（2.x 与 3.x 不兼容，见 arduino-track.md 迁移表）。

## 自检清单（交付前逐项过）

- [ ] 芯片、模组、框架（含版本）已确认或声明为默认假设
- [ ] 引脚分配表完整，禁区逐项核对（strapping/flash/input-only/USB-JTAG/ADC2∩WiFi）
- [ ] 所有 ISR：IRAM_ATTR、短小、FromISR、volatile、清标志
- [ ] 所有 `xTaskCreate*`：栈按字节、有让出路径、优先级规划合理
- [ ] NVS 先于 WiFi；NVS 写有 commit；WiFi 事件驱动且断连重连
- [ ] 所有等待带超时与失败分支；初始化用 ESP_ERROR_CHECK、运行路径用 ESP_RETURN/GOTO_ON_ERROR
- [ ] DMA 缓冲内部 RAM；PSRAM 用途正确（大缓冲 ps_malloc/PSRAM caps）
- [ ] sdkconfig.defaults 已提交（sdkconfig 本体不入库）；分区表与 Flash Size 一致
- [ ] （纪律模式）validate_esp_generated.py 已跑且 VIOLATION=0，WARNING 已逐条解释
- [ ] 已声明"未经编译/上板验证"并给出验证命令（idf.py build → flash → monitor）

## 资源（行内是"何时读"信号；细节在文档内，按需打开）

| 文件 | 何时读 |
|---|---|
| `references/esp-idf-basics.md` | **IDF 轨每次生成前**：工程解剖/构建闭环/错误处理范式/组件模型/分区表/menuconfig |
| `references/chip-family-notes.md` | **确认芯片先读**：三芯片内核与外设对照/工具链前缀/模组命名 |
| `references/gpio-pinout-guide.md` | **分配任何引脚先读**：禁区总表/默认脚表/ADC 映射/安全引脚推荐 |
| `references/isr-and-concurrency-rules.md` | 写中断/共享数据时：上下文分类/IRAM_ATTR/临界区/ISR 模板 |
| `references/freertos-on-esp32.md` | 用任务/队列/定时器时：与 STM32 差异/栈字节/TWDT/esp_timer/内存 |
| `references/peripheral-recipes.md` | 外设配方：GPIO/UART/I2C/SPI/LEDC/ADC/NVS/gptimer/WS2812 |
| `references/wifi-networking.md` | 联网场景：STA 序列/事件状态机/ESP-NOW/MQTT/HTTP/OTA |
| `references/arduino-track.md` | **Arduino 轨每次生成前**：轨道选择/loopTask/2.x→3.x 迁移/映射表 |
| `references/ble-hid-arduino.md` | BLE HID 键盘/外设（Arduino 轨）：初始化铁律序列/报告描述符/断连重广播/2.x→3.x 迁移 |
| `references/realtime-control.md` | 高频控制环（飞控/平衡/节拍器）：节拍源/超级循环/IMU 校准/互补滤波/PID/混控/安全状态机 |
| `references/iot-gateway-patterns.md` | MQTT 生产化网关：多环境配置/连接编排/发布防御/millis 回绕/命令分发/掉电回放 |
| `references/voice-assistant-xiaozhi.md` | 语音 AI 助手（xiaozhi 转写）：安装构建/设备状态机/WebSocket+MQTT/UDP 协议/AFE 音频管线/板级工厂/防变砖 OTA |
| `references/sensor-max30102.md` | MAX30102 心率血氧：接线/寄存器初始化序列/FIFO 格式/AMPD 心率/R 比值 SpO2/量纲陷阱 |
| `references/power-and-sleep.md` | 低功耗场景：深睡范式/唤醒源/RTC_DATA_ATTR/收尾清单 |
| `references/symptom-quickref.md` | 故障排查：Guru Meditation 解码/addr2line/WDT 报文/复位原因 |
| `references/known-pitfalls.md` | 纪律模式坑位申报：71 条 症状/根因/修法（含实战项目类 36–53、传感器类 54–61、语音 AI 类 62–71） |
| `templates/main_idf.c` | IDF 裸机骨架（app_main+NVS+日志+非阻塞主循环） |
| `templates/sdkconfig.defaults` | sdkconfig 基线（日志级别/采样率/看门狗等约定项） |
| `templates/main_arduino.ino` | Arduino 副轨骨架（setup/loop+FreeRTOS 任务示例） |
| `scripts/validate_esp_generated.py` | 静态纪律检查（VIOLATION 清零才交付；厂商目录自动跳过） |
| `examples/blink_uart_demo/` | 完整可编译 IDF 试例：点灯+日志（未上板） |
| `tests/bad_sample*.c*` | 故意违规样本（含 BLE 反例/正例 .cpp），自测检查脚本用 |

## 维护与沉淀

随使用逐步完善：发现 API 写法有误、新配方/新坑/检查规则改进时，**征得用户同意后**更新对应文件，
并把进展记入 [ROADMAP.md](ROADMAP.md)；不在单次对话中强行实现未沉淀的能力。
首个实测工程（编译→烧录→上板）完成后：把实测修正写回对应文档、在本文档头部更新实测状态声明、ROADMAP 记录芯片型号与工程类型。
