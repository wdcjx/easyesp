> 何时读：为任何外设（UART/I2C/SPI/ADC/PWM/中断/唤醒源）分配具体 GPIO 之前；排查「上电不启动、进不去下载、Wi-Fi 起不来、ADC 读数全坏」时。
> 状态：知识沉淀（未上板实测；引脚事实以 Espressif 数据手册/模组手册为准，模组引脚可能少于芯片）

# 引脚分配与禁区（生成任何引脚代码前必读）

## 1. 引脚分配表纪律（承接 SKILL.md 工作流步骤 2）

每次生成外设代码前，先填下表并逐项核对；「是否踩禁区」全为否才允许写代码，踩禁区的脚必须换并记录替换：

| 外设 | 引脚 | 复用功能 | 是否踩禁区 | 备用脚 |
|---|---|---|---|---|
| （填写示例见 §7） | | | | |

## 2. 三芯片禁区总表

### 2.1 strapping 引脚（复位瞬间采样；外接上下拉可致启动失败）

| 芯片 | 引脚 | 后果 |
|---|---|---|
| esp32 | GPIO0 | 复位时为低 → 进下载模式（板上 BOOT 键即接地）；启动后可作普通 IO，勿接会把它拉低的外设 |
| esp32 | GPIO2 | 进下载模式要求低或浮空；启动时外部强上拉会阻碍下载/启动组合判定 |
| esp32 | GPIO5 | 复位时决定 SDIO 从机时序（默认内部上拉）；启动后可正常使用 |
| esp32 | GPIO12 (MTDI) | 复位时为高 → flash 电压切到 1.8V，3.3V flash 模组直接启动失败；严禁外接上拉或上拉型外设 |
| esp32 | GPIO15 (MTDO) | 复位时为低 → 静默 ROM 启动日志；启动后可正常使用 |
| esp32s3 | GPIO0 | 复位时为低 → 进下载模式（BOOT 键） |
| esp32s3 | GPIO3 | 决定 JTAG 信号来源选择（极性以手册为准）；启动后可用 |
| esp32s3 | GPIO45 | 决定 VDD_SPI（flash/PSRAM 供电）电压，接错上下拉可致 flash 无法工作（同经典 GPIO12 性质） |
| esp32s3 | GPIO46 | 与 GPIO0 组合决定启动模式，并控制 ROM 日志输出 |
| esp32c3 | GPIO2 | 正常启动要求为高（默认内部上拉）；复位时被外部拉低 → 启动失败/未定义状态 |
| esp32c3 | GPIO8 | 正常启动要求为高（默认内部上拉）；外接强下拉外设会阻止启动 |
| esp32c3 | GPIO9 | 复位时为低 → 进下载模式（BOOT 键）；启动后可作普通 IO |

### 2.2 input-only（仅 esp32）

GPIO34、35、36、39 只能输入，且无内部上/下拉电阻：分压、上拉必须用实体电阻。不能作任何输出，不能开 I2C（需开漏输出）。esp32s3 / esp32c3 无 input-only 脚。

### 2.3 flash / PSRAM 占用（绝对不可用）

| 芯片 | 占用脚 | 说明 |
|---|---|---|
| esp32 | GPIO6-11 | 模组内 flash 直连 |
| esp32 | GPIO16/17（仅 WROVER 类带 PSRAM 模组） | PSRAM CS/CLK |
| esp32s3 | GPIO26-32 | Quad flash（WROOM-1 系均占用） |
| esp32s3 | GPIO33-37（Octal 模组，如 N16R8） | Octal PSRAM 额外占用到 GPIO37，以模组手册为准 |
| esp32c3 | GPIO11-17 | 芯片内置 flash 占用 |

### 2.4 USB Serial-JTAG 复用

| 芯片 | USB 脚 | 说明 |
|---|---|---|
| esp32s3 | GPIO19 (D-) / GPIO20 (D+) | 板载 Type-C 直连这两脚时不可再作 GPIO；若该板用 UART 桥芯片则 19/20 可用 |
| esp32c3 | GPIO18 (D-) / GPIO19 (D+) | 同上（常见 C3 SuperMini 等直连 USB，18/19 已被占） |
| esp32 | 无原生 USB | GPIO1/3（UART0）经 CP2102/CH340 转 USB；烧录与日志均走 UART0 |

## 3. GPIO matrix：数字外设几乎任意脚

- 概念：UART、I2C、SPI、LEDC 输出、I2S、时钟输出等数字外设经 GPIO matrix / IO_MUX 可映射到几乎所有引脚；GPIO 中断同样任意输入脚。代码不指定引脚时用默认脚。
- 常用默认脚（Arduino 侧以所用板 variant 文件为准）：

| 外设 | esp32 | esp32s3 | esp32c3 |
|---|---|---|---|
| UART0 TX/RX（日志/烧录） | GPIO1 / GPIO3 | GPIO43 / GPIO44 | GPIO21 / GPIO20 |
| Arduino Wire SDA/SCL | 21 / 22 | 8 / 9 | 8 / 9 |
| Arduino SPI MOSI/MISO/SCK/SS | 23 / 19 / 18 / 5（VSPI） | 11 / 13 / 12 / 10 | 6 / 5 / 4 / 7 |

- 固定映射例外（只能用指定脚，matrix 挪不动）：ADC、DAC（仅经典 GPIO25/26）、触摸、RTC GPIO、深度睡眠唤醒源、USB D+/D-。
- 高速 SPI 经 GPIO matrix 有时钟上限（经典约 26MHz、S3 约 40MHz，以 IDF 文档为准）；要 80MHz 必须用 IO_MUX 直连脚（经典 VSPI=18/19/23、HSPI=14/12/13）。

## 4. ADC 通道映射表

| 芯片 | ADC1（Wi-Fi 安全） | ADC2（Wi-Fi 冲突） |
|---|---|---|
| esp32 | GPIO32-39（8ch，如 GPIO34=ADC1_CH6） | GPIO0,2,4,12,13,14,15,25,26,27（10ch） |
| esp32s3 | GPIO1-10（10ch） | GPIO11-20（10ch） |
| esp32c3 | GPIO0-4（5ch） | GPIO5（仅 1ch） |

铁律：ADC2 与 Wi-Fi 同时使用必失败——Wi-Fi 驱动独占 ADC2，读取返回 ESP_ERR_TIMEOUT 或脏值（三芯片同）。凡项目用 Wi-Fi，模拟输入（电池检测等）一律选 ADC1 脚。

## 5. RTC GPIO 与深度睡眠

深睡唤醒脚属固定映射：esp32 = RTC GPIO（0,2,4,12-15,25-27,32-39）；esp32s3 = GPIO0-21；esp32c3 = GPIO0-5。唤醒源配置与功耗细节见同目录 power-and-sleep.md。

## 6. 安全引脚推荐（无坑，新手直接用）

| 芯片 | 推荐 GPIO | 避让说明 |
|---|---|---|
| esp32 | 4,13,14,16,17,21,22,23,25,26 | 16/17 在 WROVER 上被 PSRAM 占（换 27,32,33）；25/26 兼 DAC 脚但可作普通 IO；34-39 只能输入 |
| esp32s3 | 4,5,6,7,15,16,17,18,21,48 | 避开 19/20(USB)、43/44(UART0)、0/3/45/46(strap)、26-37(flash/PSRAM)；备选 8-14、47 |
| esp32c3 | 0,1,3,4,6,7,10 | 5 是 ADC2 唯一脚（Wi-Fi 冲突，勿作电池检测）；20/21 是 UART0；2/8/9 strapping 慎用；11-17 flash |

## 7. 冲突检查示例（已填样表）

场景：经典 esp32——UART0 日志 + I2C OLED + LEDC 舵机 + ADC 电池检测。

| 外设 | 引脚 | 复用功能 | 是否踩禁区 | 备注 |
|---|---|---|---|---|
| UART0 日志 | TX=GPIO1 RX=GPIO3 | UART0 默认 | 否 | 与 USB 桥共线，不再外接设备 |
| I2C OLED (SSD1306) | SDA=GPIO21 SCL=GPIO22 | GPIO matrix | 否 | 模块自带或外加 4.7k 上拉 |
| LEDC 舵机 50Hz | GPIO18 | GPIO matrix | 否 | 舵机独立 5V 供电，必须共地 |
| ADC 电池检测 | GPIO34 | ADC1_CH6 | 否（input-only 只输入，不算禁区） | 电阻分压到 0-3.3V；GPIO34 无内部上拉，必须实体电阻；选 ADC1 避开 Wi-Fi 冲突 |

核对结论：无 GPIO6-11、无 strapping、无 ADC2、无 USB 复用冲突 → 通过。
反例教训：电池检测若误选 GPIO25（ADC2_CH8），Wi-Fi 一启动读数必坏；正确做法是换 ADC1 脚（32/33/34/35 等），而不是改代码。
