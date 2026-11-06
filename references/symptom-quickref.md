# 症状速查（看到什么报文→先查什么）

> 何时读：拿到错误日志/异常复位现象，先用本文把报文翻译成排查方向，再跳 known-pitfalls.md 对应编号。
> 状态：知识沉淀（未上板实测；API/报文对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

## 1. 排查方法论（三步）

1. 查复位原因：app_main 早段打印 `esp_reset_reason()`，按 §2 表翻译；配合串口首行 ROM 输出如 `rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)`、`rst:0xc (SW_CPU_RESET)`（码以官方文档为准）。
2. 读日志结构：`E (356742) wifi: xxx` = 级别（启动以来毫秒）TAG: 内容。E>Error W>Warn I>Info，D/V 递减；TAG 指明出错组件栈；时间戳判断周期/风暴/时长。
3. 按 §3–§7 对号定位方向，最终落到 known-pitfalls.md 编号（§8 总表）。

## 2. esp_reset_reason_t 全表（esp_reset_reason.h）

| 枚举 | 中文 | 典型触发 → pitfall |
|---|---|---|
| ESP_RST_POWERON | 上电复位 | 正常上电 |
| ESP_RST_EXT | 外部引脚复位 | EN/RST 键（classic 头文件注明不适用，以注释为准） |
| ESP_RST_SW | 软件复位 | esp_restart()、OTA 激活重启 |
| ESP_RST_PANIC | 异常复位 | Guru Meditation/abort() 后自动重启 → §3 |
| ESP_RST_INT_WDT | 中断看门狗复位 | ISR 过长 → 8 |
| ESP_RST_TASK_WDT | 任务看门狗复位 | 忙循环/饿死 IDLE → 7/9/10 |
| ESP_RST_WDT | 其他看门狗 | RTC WDT 等启动阶段超时；偶发先怀疑供电/启动早期卡死 |
| ESP_RST_DEEPSLEEP | 深睡唤醒 | 正常（非故障）；周期异常/误醒 → 30 |
| ESP_RST_BROWNOUT | 欠压复位 | 供电不足 → 1 |
| ESP_RST_UNKNOWN | 无法判定 | 启动早期掉电/异常，结合串口首行与硬件复查 |

## 3. Guru Meditation Error 解码

### 3.1 报文样例（classic ESP32，Xtensa；地址为示意）

```
Guru Meditation Error: Core  0 panic'ed (LoadProhibited). Exception was unhandled.
Memory contents at 0x3ffb4d24: 00000000 00000000 3ffb8000 3ffb8000

EXCVADDR: 0x00000000

Backtrace: 0x400824e9:0x3ffb4d00 0x400d3c11:0x3ffb4d20 0x400d0f2a:0x3ffb4d90
```

C3（RISC-V）句式相同，如 `Guru Meditation Error: Core  0 panic'ed (StoreProhibited). Exception was unhandled.`；完整异常名集以官方文档为准。

### 3.2 逐段解释

| 片段 | 含义 | 用法 |
|---|---|---|
| `Core  0` | 出错 CPU（双核另一为 Core  1；Core 后两空格为固定格式） | 区分协议栈核/应用核 |
| `panic'ed (Xxx)` | panic 原因（Xtensa 为 EXCCAUSE 译名） | 查 §3.3 表 |
| `Memory contents at 0x...` | 出错栈附近内存 dump | 辅助判断被踩内容 |
| `EXCVADDR: 0x...` | 出错的访问地址 | 0x0/极小值=空/野指针；落在栈区=栈溢出嫌疑 |
| `Backtrace: PC:SP PC:SP ...` | 调用链回溯，成对出现 | 只取每对前一个 PC 去解码 |

### 3.3 panic 原因高频表（EXCCAUSE 常见项）

| 原因串 | 机制 | 最常见根因 → pitfall |
|---|---|---|
| LoadProhibited / StoreProhibited | 非法地址读/写 | 野指针、未初始化句柄、栈溢出踩帧 → 15/22 |
| InstrFetchProhibited（Xtensa 亦作 InstructionFetchError 等，名称随芯片/译码而异，以官方文档为准） | 非法取指 | 坏函数指针、返回地址被踩、cache 禁用窗口 ISR 未入 IRAM → 11 |
| IllegalInstruction | 执行非法指令 | 跳进数据区执行、内存踩踏 → 22 |
| Cache disabled but cached memory region accessed | flash 擦写窗口访问 flash 内代码/常量 | ISR 漏 IRAM_ATTR → 11 |
| Interrupt wdt timeout on CPU0/1 | 中断看门狗 | ISR 太长/临界区过久 → 8 |
| Stack canary watchpoint triggered (xxx)；或 `***ERROR*** A stack overflow in task xxx has been detected.` | 任务栈溢出守卫 | 栈太小或单位当字 → 22 |

### 3.4 backtrace 解码命令

- 首选 `idf.py monitor`：自动把 Backtrace 的 PC 就地解码为 `函数 at 文件:行号`（要求 build 目录 elf 与烧录固件同一次构建）。
- 手动解码（只取每对的 PC，忽略 SP）：
  - esp32 / esp32s3（Xtensa，IDF 5 统一工具链）：`xtensa-esp-elf-addr2line -pf -e build/app.elf 0x400824e9 0x400d3c11`
  - 旧版分离工具链名：`xtensa-esp32-elf-addr2line` / `xtensa-esp32s3-elf-addr2line`
  - esp32c3（RISC-V）：`riscv32-esp-elf-addr2line -pf -e build/app.elf 0x42001234`
- 输出 `??`：地址在 ROM/未链接段或 elf 与固件不匹配。
- 启用 CONFIG_ESP_COREDUMP 可离线分析 core dump（esp-coredump/GDB）。

## 4. 看门狗报文逐词解读（IDF 5.x）

```
E (10541) task_wdt: Task watchdog got triggered. The following tasks/users did not reset the watchdog in time:
E (10541) task_wdt:  - IDLE0 (CPU 0)
E (10541) task_wdt: Tasks currently running:
E (10541) task_wdt: CPU 0: busy_task
E (10541) task_wdt: Aborting.
```
（时间戳/任务名为示意；`Aborting.` 后续输出随版本/配置略有差异，以官方文档为准。）

- `Task watchdog got triggered. The following tasks/users did not reset the watchdog in time:`——开场：下列任务/用户超时未喂狗。
- `- IDLE0 (CPU 0)`：受害者是 IDLE0 → 被更高优先级饿死，看下一行抓真凶；若此处是业务任务名 → 它自己在忙循环（→ 7）。
- `Tasks currently running:` / `CPU 0: busy_task`：正在占住 CPU 的任务 → 去它的循环里加 vTaskDelay/yield（→ 7/9/10；Arduino 则是 loopTask，→ 9）。
- `Aborting.`：CONFIG_ESP_TASK_WDT_PANIC=y 时随即 abort() 重启，复位原因 ESP_RST_TASK_WDT。
- 中断看门狗不走上述格式，直接 Guru：`Guru Meditation Error: Core  0 panic'ed (Interrupt wdt timeout on CPU0). Exception was unhandled.`（→ 8）。

## 5. abort() / assert failed 报文

```
abort() was called at PC 0x400d3f52 on core 0
```
PC 直接送 addr2line；来源常见：断言失败、TWDT panic、堆错误 abort（看紧邻 heap 校验行）。

```
assert failed: xQueueSemaphoreTake queue.c:1549 (pxQueue->uxItemSize == 0)
```
- 格式：`函数 文件:行号 (断言表达式)`；翻到组件内该行看前提——多为句柄类型不对、未初始化就调用、ISR 调任务级 API（→ 13）。
- 栈溢出兄弟款：`***ERROR*** A stack overflow in task xxx has been detected.`（→ 22）。

## 6. 烧录失败速查

```
A fatal error occurred: Failed to connect to ESP32: Timed out waiting for packet header
```
```
A fatal error occurred: Failed to connect to ESP32-C3: No serial data received.
```
（第二行多见于 C3/S3 原生 USB；措辞随 esptool 版本略有差异，以官方文档为准。）

处置顺序：
1. 手动进下载模式：按住 BOOT（C3=GPIO9、S3=GPIO0）→ 按一下 EN/RST → 松 BOOT → 重试（→ 4）。
2. 降波特率：`idf.py flash -b 115200`。
3. 线与口：换带数据的 USB 线、直插主板 USB 口、确认驱动（CP210x/CH34x/原生 USB-CDC）。
4. 外围与供电：strapping 被外围拉错（→ 3/4）；供电不稳（→ 1）。
5. 端口占用：PermissionError(13)=monitor/串口助手未关，monitor 内 Ctrl+] 退出（→ 32）。

## 7. 网络日志与 disconnect reason

- `E (356742) wifi: ...`：WiFi 驱动层错误；短时间内连发=重连风暴（→ 27），叠加供电弱会触发 brownout（→ 1）。
- 事件 WIFI_EVENT_STA_DISCONNECTED 携带 `reason`（枚举见 esp_wifi_types.h WIFI_REASON_*），高频 10 码速查：

| reason | 名称 | 含义 → 先查 |
|---|---|---|
| 200 | BEACON_TIMEOUT | 与 AP 失联：距离/天线/干扰/AP 重启 |
| 201 | NO_AP_FOUND | 扫不到目标 AP：SSID 拼写、2.4G/5G 频段、信道与国家码、信号 |
| 15 | 4WAY_HANDSHAKE_TIMEOUT | 四次握手超时：密码错误最常见 |
| 2 | AUTH_EXPIRE | 认证超时：弱信号、AP 拒绝 |
| 202 | AUTH_FAIL | 认证失败：密码错/加密方式不匹配（WPA2/WPA3/混合模式） |
| 203 | ASSOC_FAIL | 关联被拒：AP 满员、MAC 过滤 |
| 204 | HANDSHAKE_TIMEOUT | 握手整体超时（链路质量差） |
| 205 | CONNECTION_FAIL | 连接流程综合失败 |
| 4 | ASSOC_EXPIRE | AP 侧超时/不活跃踢人 |
| 1 | UNSPECIFIED | 未分类：常见 AP 主动踢/漫游 |

- 断连重连范式（DISCONNECTED 里 esp_wifi_connect）见 pitfall 27；MQTT 截断见 28。

## 8. 一页总表（症状关键词 → 先查 → pitfall 编号）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| Brownout detector was triggered | 电源功率/线/电容 | 1 |
| 上电不启动＋GPIO12 被拉高 | flash 电压 strapping | 2 |
| 无法启动/意外进下载模式 | strapping 脚外围 | 3/4 |
| 烧录成功但 boot loop | Flash Size/分区表 | 5 |
| 选脚无信号 | 模组引脚图/input-only | 6/20 |
| Task watchdog got triggered | 正在运行任务的循环加 delay | 7/9/10 |
| Interrupt wdt timeout | ISR 瘦身＋IRAM_ATTR | 8 |
| Cache disabled but cached memory | IRAM_ATTR/ESP_INTR_FLAG_IRAM | 11 |
| ISR 内打印后死机 | ISR 禁 printf/ESP_LOG | 12 |
| ISR 调 API 随机崩 | FromISR 系列/漏 yield/volatile | 13/14/15 |
| 开 WiFi 后 ADC 失效 | 换 ADC1 脚 | 16 |
| LEDC 无输出 | 频率×分辨率上限/查返回值 | 17 |
| I2C 超时/SDA 拉死 | 9 脉冲总线恢复 | 18 |
| UART 丢段 | rx buffer/及时读/flush | 19 |
| GPIO34–39 无输出 | input-only | 20 |
| S3/C3 串口/下载消失 | USB-JTAG 脚被占用 | 21 |
| 栈溢出/随机 Prohibited | 栈字节单位/加大栈 | 22 |
| 大缓冲分配 NULL | PSRAM 配置/heap_caps | 23 |
| DMA 数据花 | MALLOC_CAP_DMA/对齐 | 24 |
| 定时器/事件/MQTT 全卡 | 回调里长阻塞 | 25 |
| esp_wifi_init 失败含 0x1101 | nvs_flash_init 先行 | 26 |
| 断网永不重连 | DISCONNECTED 里 connect | 27 |
| MQTT 长消息截断 | buffer.size/out_buffer.size | 28 |
| 深睡后电平漂移 | gpio_hold | 29 |
| 深睡误唤醒 | 唤醒脚外部上下拉 | 30 |
| 换 target 编译乱 | fullclean＋set-target | 31 |
| PermissionError(13) | 关 monitor 再烧 | 32 |
| Windows 构建随机错 | 纯 ASCII 无空格路径 | 33 |
| ledcSetup 未定义 | Arduino 3.x 新 LEDC API | 34 |
| 注释/字符串乱码 | 统一 UTF-8 | 35 |
