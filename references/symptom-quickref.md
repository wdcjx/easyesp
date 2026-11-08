# 症状速查（看到什么报文→先查什么）

> 何时读：拿到错误日志/异常复位现象，先用本文把报文翻译成排查方向，再跳 known-pitfalls.md 对应编号。
> 状态：知识沉淀（未上板实测；API/报文对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）。症状→编号映射覆盖 #1–165 全量：基础类见 §8，实战工程类（#36–165，含 MicroPython / Modbus / BLE 小程序外设 / POV 风扇屏 / ESP32-CAM 双机）见 §9

## 1. 排查方法论（三步）

1. 查复位原因：app_main 早段打印 `esp_reset_reason()`，按 §2 表翻译；配合串口首行 ROM 输出如 `rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)`、`rst:0xc (SW_CPU_RESET)`（码以官方文档为准）。
2. 读日志结构：`E (356742) wifi: xxx` = 级别（启动以来毫秒）TAG: 内容。E>Error W>Warn I>Info，D/V 递减；TAG 指明出错组件栈；时间戳判断周期/风暴/时长。
3. 按 §3–§7 对号定位方向，最终落到 known-pitfalls.md 编号（§8 基础类总表 / §9 实战工程类总表）。

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

## 8. 一页总表·基础类（症状关键词 → 先查 → pitfall 编号，#1–35）

> 实战工程类坑位（#36–124：BLE HID / 飞控 / IoT 网关 / 传感器 / 语音 AI / 电机 / 量产 / 教育机器人 / MicroPython / Modbus 主机）见 §9；#125–138 BLE 小程序外设见 §9.9；#139–153 POV 风扇屏见 §9.10；#154–165 ESP32-CAM 双机小车见 §9.11。

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

## 9. 一页总表·实战工程类（症状关键词 → 先查 → pitfall 编号，#36–124）

与 known-pitfalls.md 类目一一对应；症状关键词取自各坑首栏，详见对应编号行。

### 9.1 BLE HID / 飞控 / IoT 网关（36–53，源：ble-hid-arduino / realtime-control / iot-gateway-patterns）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| BLE 断连后手机再也搜不到设备 | onDisconnect 重启广播 | 36 |
| HID 报告换台手机失灵 | REPORT_ID 约定两侧统一 | 37 |
| 节拍器/周期任务越跑越偏 | 增量对拍替代 delay | 38 |
| 按键按一下对端连发多次 | 沿检测＋一次性标志 | 39 |
| 媒体键（播放/音量）无效 | 独立 Consumer 报告 | 40 |
| 软 I2C OLED 花屏/半屏 | 硬件 Wire 或开漏+ACK | 41 |
| 切模式后原按键"卡住" | 切换前发全零报告 | 42 |
| 换 IMU/改朝向姿态疯转 | 轴映射行重写+物理验证 | 43 |
| 飞行中调参瞬间抽动掉高 | 飞行态禁写 NVS | 44 |
| 加油门瞬间复位循环 brownout | 电源余量/母线电容 | 45 |
| 单电机测试转时不转 | 改占空前等 PWM 周期 | 46 |
| QGC 连不上飞控 WiFi | 固件定期广播心跳 | 47 |
| 悬停缓慢漂移 | landed 才做加计校正 | 48 |
| PubSubClient 发大 JSON 失败 | setBufferSize ≥消息+512B | 49 |
| publish 返回 1 但服务器没收到 | 发布防御四连 | 50 |
| 连续 49.7 天后 TTL 全错乱 | 无符号差值判周期 | 51 |
| 服务器拒收多空字段 JSON | 空字段发 null/降平面格式 | 52 |
| DNS 正常但 MQTT 连不上 | 预解析+TCP 探活绕域名 | 53 |

### 9.2 传感器 MAX30102（54–61，源：sensor-max30102）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| MPY 固件指位恒 0"未检测到手指" | 读数移位量纲 ÷8 | 54 |
| I2C 无 ACK / Sensor connection failed | scan() 应见 0x57 | 55 |
| 波形断续、脉冲缺拍 | FIFO 批量读+OVF 检查 | 56 |
| BPM 乱跳偶发尖峰 | 滤波后找峰+RR 中值 | 57 |
| SpO2 周期性跳 0 | 有效窗判定+剔野 | 58 |
| 自改采样率后心率血氧全乱 | 锁定 50Hz 有效输出 | 59 |
| SpO2 大幅偏离而心率正常 | Red/IR 字节序 | 60 |
| 噪声大、漂、模块发热 | 降亮度验证/供电去耦 | 61 |

### 9.3 语音 AI xiaozhi（62–71，源：voice-assistant-xiaozhi）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 编不过/ABI 报错；C3 Wi-Fi init 失败 | IDF 6.x 分支（非 tag） | 62 |
| 4MB flash 收不到 OTA | 4m.csv 无 ota 分区 | 63 |
| 无 PSRAM 唤醒词无效/说话卡死 | AFE 依赖 SPIRAM | 64 |
| 对话中途卡死无声 | 发送失败清空队列 | 65 |
| 烧错板型：无声/引脚错乱 | 板目录逐字核对 | 66 |
| 开着音箱唤醒不了/自打断 | AEC 参考通道硬件 | 67 |
| "No websocket section found" | OTA 接口下发配置链 | 68 |
| device/server AEC 同开编译失败 | 二者互斥只开一 | 69 |
| 4G 板收事件再发数据死机 | Schedule 到主任务发 | 70 |
| MCP 工具调用偶发不响应 | 工具数量+前置排列 | 71 |

### 9.4 电机控制 FOC/CAN（72–81，源：motor-control-foc）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 总线一次异常后 CAN 永久静默 | BUS_OFF recovery+重启 | 72 |
| 蓝牙断连后沿旧指令行驶 | 指令超时清零 | 73 |
| 每换一块板手改零偏重烧 | 静止自校准+NVS 存储 | 74 |
| 角速度读数整体偏小 8 倍 | 量程档与换算系数一致 | 75 |
| 跌倒保护分支卡死不退出 | 保护等待加超时+WDT 注册 | 76 |
| 控制环偶发半更新数据抖动 | 临界区快照/序列锁 | 77 |
| 电池低压后输出突变 | 低压停机不伪造电压 | 78 |
| 端到端延迟抖动最坏 >6ms | 反馈内联读/提任务优先级 | 79 |
| BLE 调试帧裸读写 RAM | 量产关调试特征+配对加密 | 80 |
| 上电约 5s 无响应像死机 | LED 明示状态+黑窗日志 | 81 |

### 9.5 量产手册（82–93，源：production-readiness）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 空闲内存够却 malloc 失败 | largest_free_block/静态分配 | 82 |
| 链接错 iram0.text 放不下 | 只给 ISR 加 IRAM_ATTR | 83 |
| 随机重启/数据错乱无规律 | 栈溢出检测+水位 <200 字加栈 | 84 |
| 解深层 JSON/遍历目录崩溃 | 任务内禁递归 | 85 |
| WiFi connected 但 MQTT/云不通 | 双层保活（链路+应用） | 86 |
| 弱网下越忙越连不上雪崩 | 心跳限流+QoS 分级+降频 | 87 |
| NVS 越用越慢/NO_FREE_PAGES | 延迟写+变更才写 | 88 |
| 启动慢；深睡唤醒后 WiFi 不稳 | PHY 校准数据入 NVS | 89 |
| 定时唤醒周期越跑漂移越大 | 外部 32.768kHz 晶振 | 90 |
| 弱网 OTA 反复从头下载 | NVS 记偏移断点续传 | 91 |
| 串口拖慢系统/printf 栈溢出 | 日志分级+Newlib Nano | 92 |
| OTA 途中被配网/复位打断变砖 | 升级互斥锁 | 93 |

### 9.6 教育机器人 Mind+（94–101，源：mindplus-robot-ext）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 直流电机啸叫/低速抖/H 桥发热 | PWM 频率 10–20kHz（非 50） | 94 |
| 想滑行却猛刹一顿顿走 | 双高=刹车，双低=滑行 | 95 |
| FpvReadByte 偶发随机值 | default 返回 0 封口 | 96 |
| 自写校验和移植后总错 | `&` 高于 `^`，加括号 | 97 |
| 一键起飞/降落偶发丢失 | 命令沿检测，环 <200ms | 98 |
| 旧 .mp 案例没有新功能 | 内嵌旧库，重新拖积木 | 99 |
| 两种模式积木只认一个 | addSetup 键名含模式 | 100 |
| mcpwm_init 找不到/deprecation | IDF 5.2+ 新 MCPWM/PCNT API | 101 |

### 9.7 MicroPython 商用工程（102–115，源：micropython-env-controller）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| microdot 保存大配置(>16KB)静默失败 | max_content_length 上限 | 102 |
| 整机"卡死"无异常日志、网络全断 | IOQueue OSError 补丁 | 103 |
| Web/控制周期性卡顿数百 ms | gc.threshold 小步+免 SD 落盘 | 104 |
| 首次请求后刷 `spi transmit failed` | 底层对象被 GC 析构，钉引用 | 105 |
| RS485 快速响应整帧被吞/死锁 | DE 时序下沉 C | 106 |
| 9600 长帧 CRC 失败只收 20B | 帧空闲阈值提到 30ms | 107 |
| 写已执行但主机报"无响应" | 回显判定四层匹配 | 108 |
| Modbus-TCP 连断风暴压测冻结 | 单任务非阻塞+连接上限 | 109 |
| u16 寄存器 40000 显示 -25536 | 仅 s16/s32 符号扩展 | 110 |
| asyncio.sleep 后动作偶发不执行 | 自写 _sleep_ms 硬超时 | 111 |
| 服务读不到板载输入/状态时有时无 | import main 重执行，模块别名 | 112 |
| OTA"成功"但行为没变 | .py 优先于 .mpy，同步 .bak | 113 |
| MQTT 带 auth 被 RST；断线永不重连 | umqtt 编码 bug，自写客户端 | 114 |
| OTA 升级包损坏直接变砖 | tar 校验链+.mpy 绑定+回滚 | 115 |

### 9.8 Modbus / RS-485 主机（116–124，源：modbus-rtu-485）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 每次事务耗满超时、CPU 空转 | 字节间隔判帧完+yield | 116 |
| 读 >29 寄存器必报 TIMEOUT | 缓冲 ≥5+2N+2 | 117 |
| slave=0/quantity=0 照发不误 | 调用前自校验参数 | 118 |
| lun 传大后内存静默写坏 | 入口边界检查 | 119 |
| 从机收到截尾请求帧/CRC 错 | wait_tx_done 再拉低 DE | 120 |
| 干扰后连续多轮 CRC 错又自愈 | 溢出进丢弃模式待静默 | 121 |
| 广播写单寄存器误报超时 | slave==0 跳过等待 | 122 |
| 发送期间收到"幻影数据" | DE+/RE 接法+发前清缓冲 | 123 |
| 高频轮询吞吐折损 10%+ | DE 延时 µs 级/硬件 RS485 | 124 |

### 9.9 BLE / 微信小程序外设（125–138，源：ble-weapp-morse-trainer）

| 症状关键词 | 先查 | pitfall |
|---|---|---|
| 手机断开后再也搜不到设备 | onDisconnect 重启广播 | 125 |
| 下发长文本后蓝牙卡死数秒 | onWrite 内不做长活 | 126 |
| 电键未按乱触发/换脚后失效 | 每脚显式 pinMode | 127 |
| 按住按键上电进下载模式 | GPIO0 strapping 冲突 | 128 |
| 未触摸偶发误判按下 | touchRead==0 二次读 | 129 |
| 快速连发 BLE 消息内容错乱 | 共享 String 无锁 | 130 |
| 调用改参后 undefined reference | 声明/定义签名漂移 | 131 |
| 设置面板连点 NVS 写入暴涨 | Preferences 键值级 | 132 |
| 参数 >99999 截断/float 失真 | 定长文本落盘宽度 | 133 |
| "字母间隔"设置改了没反应 | 条件/延时变量错位 | 134 |
| 写入异常帧后死机/复位 | 冒号分割越界写栈 | 135 |
| 自动键无 iambic 交替节奏 | 自捶 delay 阻塞采集 | 136 |
| 连接间隔只生效一个设置 | setMinPreferred 后者覆盖 | 137 |
| 长时间运行 BLE 变慢/堆碎片 | String 码表+拼接分配 | 138 |

### 9.10 POV 风扇屏 / WS2812 阵列（139–153，源：pov-fan-display）

| 症状 | 先查 | 编号 |
|---|---|---|
| 上传 JPEG 显示全黑、视频正常 | C 整数除法亮度缩放恒 0 | 139 |
| 全新 flash 首启即崩 | 空 FS 裸 fopen NULL | 140 |
| 帧数多计一/尾部花屏 | feof 先判后读+魔法 -2 | 141 |
| MQTT 收到的文件只剩一小段 | 分块事件被逐个覆盖写 | 142 |
| 设备回发大图 APP 收不到 | publish 超 out_buffer 静默丢 | 143 |
| 任意人能读/删设备文件 | 路径穿越+CORS\*无认证 | 144 |
| 公网陌生人可遥控电机 | 账密三处明文泄露 | 145 |
| 100kHz ISR CPU 占用高 | ISR 非幂二模除+参数名义不符 | 146 |
| 输出脚电平中间态抖动 | 上下拉同时使能打架 | 147 |
| 多灯带改分频后时序全乱 | 组件全局 tick 被共享 | 148 |
| POV 红蓝与原图对调 | BGR/RGB 换序差异 | 149 |
| 第 10 页图调不出来 | 000%d 与 0010 文件名漂移 | 150 |
| 大图/非 160×160 花屏堆损 | 截断+固定尺寸缓冲越界 | 151 |
| wav 快放变声/头杂音 | 44100+44 字节头写死 | 152 |
| app 分区莫名紧张 | 455KB 死资源 EMBED | 153 |

### 9.11 ESP32-CAM / 双机协处理（154–165，源：esp32cam-stm32-bridge）

| 症状 | 先查 | 编号 |
|---|---|---|
| 对端发半行数据网页卡 1 秒 | readStringUntil 默认 1000ms 超时饿死 loop | 154 |
| 换一份 uart 实现后读数全 0 | CSV 与 JSON 双实现协议漂移 | 155 |
| 按文档接新对端命令失灵 | 单字符下行无换行、靠立即执行语义 | 156 |
| 松开却回 ACK:AUTO_TRACK | 复制粘贴旧版 ACK 文案 | 157 |
| 147KB camera_index.h 拖累编译 | 未调用的官方示例死代码 | 158 |
| 改 partitions.csv 无效果 | Arduino 不读 sketch 目录分区表 | 159 |
| 摄像头工程加 PWM 后画面异常 | XCLK 占 LEDC ch0/timer0+宏撞名 | 160 |
| AP 失败后设备消失无指示 | while(1) 静默停机 | 161 |
| SD 卡怎么初始化都失败 | SD 引脚组被 UART2/闪光灯瓜分 | 162 |
| 交叉接线共 3.3V 仍乱码 | 跨板没共地 | 163 |
| STM32 侧某轮方向失控 | PB3/PB4 未 SWJ remap | 164 |
| 双标签看视频控制变卡 | 单线程 send_P 整帧阻塞 /control | 165 |
