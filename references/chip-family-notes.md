> 何时读：选型或跨芯片移植代码时；排查「这块板为什么没有这个外设/引脚/命令」时。分配具体引脚前必读同目录 gpio-pinout-guide.md。
> 状态：知识沉淀（未上板实测；引脚事实以 Espressif 数据手册/模组手册为准，模组引脚可能少于芯片）

# 三芯片家族对照（esp32 / esp32s3 / esp32c3）

## 1. 总表

| 维度 | esp32（经典） | esp32s3 | esp32c3 |
|---|---|---|---|
| 内核 | Xtensa LX6 双核 240MHz | Xtensa LX7 双核 240MHz | RISC-V RV32IMC 单核 160MHz |
| 片上 SRAM | 约 520KB | 约 512KB | 约 400KB |
| 片上 ROM | 448KB | 384KB | 384KB |
| 原生 USB | 无（模组走 UART 桥：CP2102/CH340） | USB OTG (FS) + USB Serial-JTAG | 仅 USB Serial-JTAG（无 OTG） |
| 芯片 GPIO 数（数量级） | 34 | 45 | 22（模组实际引出更少，以模组为准） |
| JTAG | 专用脚 GPIO12-15（MTDI/MTCK/MTMS/MTDO） | USB Serial-JTAG，或直连 MTCK 组 GPIO39-42 | 仅 USB Serial-JTAG（GPIO18/19） |
| 温度传感器 | 无（用外置 NTC/数字传感器） | 有（temperature_sensor_install/_enable/_read_celsius） | 有（同 S3 API） |
| PSRAM | 仅 WROVER 类模组（占 GPIO16/17） | 模组集成（Quad 或 Octal） | 无 |
| 无线 | Wi-Fi 4 + BT4.2（BR/EDR + BLE） | Wi-Fi 4 + BLE 5（无 BR/EDR） | Wi-Fi 4 + BLE 5（无 BR/EDR） |

## 2. 外设资源差异表

| 外设 | esp32 | esp32s3 | esp32c3 |
|---|---|---|---|
| UART 控制器 | 3 | 3 | 2 |
| I2C 控制器 | 2 | 2 | 1 |
| 通用 SPI（GP-SPI，不含 flash 专用 SPI0/1） | 2（SPI2=HSPI、SPI3=VSPI） | 2（SPI2、SPI3） | 1（仅 SPI2） |
| LEDC PWM 通道 | 16（8 高速 + 8 低速） | 8（仅低速） | 6（仅低速） |
| LEDC 高速模式 | 支持 LEDC_HIGH_SPEED_MODE | 仅 LEDC_LOW_SPEED_MODE，传高速模式会 assert | 仅 LEDC_LOW_SPEED_MODE，传高速模式会 assert |
| RMT 通道 | 8（TX/RX 可配，以 IDF 文档为准） | 4 TX + 4 RX | 2 TX + 2 RX |
| ADC 单元 / 通道数 | 2：ADC1=8ch、ADC2=10ch | 2：ADC1=10ch、ADC2=10ch | 2：ADC1=5ch、ADC2=1ch（GPIO 对照见 gpio-pinout-guide.md） |
| DAC | 2（GPIO25=DAC1、GPIO26=DAC2） | 无 | 无 |
| 触摸传感 | 10ch（GPIO0,2,4,12-15,27,32,33） | 14ch（GPIO1-14） | 无 |

## 3. 工具链与命令差异

| 项 | esp32 | esp32s3 | esp32c3 |
|---|---|---|---|
| idf.py 目标名 | esp32 | esp32s3 | esp32c3 |
| 工具链前缀 | xtensa-esp-elf | xtensa-esp-elf | riscv32-esp-elf |
| addr2line | `xtensa-esp-elf-addr2line -pfiaC -e build/app.elf 0x40123abc` | 同 esp32 | `riscv32-esp-elf-addr2line -pfiaC -e build/app.elf 0x42001234` |
| objdump | `xtensa-esp-elf-objdump -d build/app.elf` | 同 esp32 | `riscv32-esp-elf-objdump -d build/app.elf` |
| Arduino 板名 | ESP32 Dev Module（FQBN esp32:esp32:esp32dev；开发板别名 esp32dev / ESP32-DevKitC） | ESP32S3 Dev Module（esp32:esp32:esp32s3；开发板 ESP32-S3-DevKitC-1） | ESP32C3 Dev Module（esp32:esp32:esp32c3；开发板 ESP32-C3-DevKitM-1） |

注：
- `idf.py set-target <目标>` 会清空 build/ 重新配置，属正常现象，不是报错。
- `idf.py monitor` 对 panic 栈自动符号化；手动 addr2line 用于裸地址（日志 backtrace 行、coredump 离线解析）。

## 4. 单核 vs 双核开发差异

- `xTaskCreatePinnedToCore(fn, name, stack, arg, prio, handle, core)` 的 core 合法值：
  - esp32 / esp32s3：0、1、tskNO_AFFINITY。
  - esp32c3：仅 0 或 tskNO_AFFINITY；传 1 直接 assert/abort。
- 惯例核分工（双核）：core0 = 系统/网络（Wi-Fi、lwIP、esp_timer 等 IDF 系统任务多钉在 core0）；core1 = 应用任务。硬实时任务（电机控制、精密时序）钉 core1，避开网络栈抖动。
- Arduino loopTask 所在核：esp32/esp32s3 = core1（loop() 与 Wi-Fi 栈天然分核）；esp32c3 = core0（单核，loop 与所有任务抢同一核，实时设计要留余量）。
- menuconfig：CONFIG_FREERTOS_UNICORE 可把双核芯片按单核配置运行（跨芯片兼容开关，产品少用）。

## 5. 常见模组小表

| 模组 | 芯片 | flash | PSRAM | 注意 |
|---|---|---|---|---|
| ESP32-WROOM-32 | esp32 | 4MB | 无 | 最常见；不引出 GPIO6-11 |
| ESP32-WROVER-B / WROVER-E | esp32 | 4MB | 4MB 或 8MB | GPIO16/17 被 PSRAM 占用不可用 |
| ESP32-S3-WROOM-1 N8R2 | esp32s3 | 8MB Quad | 2MB Quad | 命名：N=flash MB 数，R=PSRAM MB 数 |
| ESP32-S3-WROOM-1 N16R8 | esp32s3 | 16MB Quad | 8MB Octal | R8=Octal PSRAM：GPIO33-37 被占不可用（以模组手册为准） |
| ESP-C3-32S | esp32c3 | 4MB | 无 | 安信可模组 |
| ESP32-C3-MINI-1 | esp32c3 | 4MB | 无 | Espressif 小尺寸模组 |

提醒：模组引出的 GPIO 恒少于芯片（如 WROOM-32 不引 GPIO6-11；S3 模组未必引出 GPIO33-37），写代码前以所用模组手册的引脚图逐脚核对。

## 6. strapping 摘要

strapping 引脚在复位瞬间被采样决定启动配置（下载模式、flash 电压等），外接强上/下拉可能直接导致无法启动；三芯片完整清单与各自后果见同目录 gpio-pinout-guide.md。
