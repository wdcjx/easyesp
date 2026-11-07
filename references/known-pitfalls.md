# 已知坑清单（种子版，按使用逐步实测补充）

> 何时读：编译/烧录/运行出现任何异常症状，按关键词先来本表对号入座；报文→编号映射见 symptom-quickref.md。
> 状态：知识沉淀（#1–35 对齐官方文档、#82–93 源自用户提供的《ESP32 软件开发避坑手册（量产级）》文档，均未上板实测；**#36–81、#94–153 源自已上板工程**（用户提供的真实硬件运行项目，含 MicroPython 商用工程、Modbus 主机库、BLE 小程序外设与 POV 风扇屏）。API/报文对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

条目格式：`编号. 症状 | 根因 | 修法`（表格呈现）。编号稳定，实测补充只追加不改号。

## 启动类（1–6）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 1 | 反复重启，日志含 `Brownout detector was triggered`，多发生在 WiFi TX / 上电瞬间 | 供电不足：TX 峰值电流 200mA 级（手册典型值）令电压跌破 brownout 阈值 | 5V≥2A 电源；短粗 USB 线；模块 VCC 近端加 ≥470µF＋0.1µF 电容；不经长排线/面包板弱轨供电 |
| 2 | classic esp32 上电不启动或复位循环；GPIO12(MTDI) 外围被拉高而模组 flash 为 3.3V | GPIO12 是 strapping 脚：启动采到高电平 → VDD_SDIO=1.8V，3.3V flash 读失败 | 硬件保证上电时 GPIO12 为低；根治可烧 eFuse：`espefuse.py --port COMx set_flash_voltage 3.3V`（不可逆）；排查时先断开该脚外设 |
| 3 | strapping 脚当普通 IO 用后无法启动 / 进不了应用 / 下载模式行为怪 | 启动时刻采样：classic=GPIO0/2/4/5/12/15；S3=GPIO0/3/45/46；C3=GPIO2/8/9 | 对照 datasheet strapping 节；外围默认电平须兼容启动需求；能不用就不用；GPIO0/BOOT 复用保留按键 |
| 4 | C3/S3 无法烧录或偶发进下载模式 | 下载模式靠 strapping：C3=GPIO9（BOOT 键）、S3=GPIO0，复位时保持低 | 烧录时按住 BOOT 再按 EN；外围勿拉低 GPIO9(C3)/GPIO0(S3)；C3 的 GPIO8、S3 的 GPIO46 影响 ROM 日志/JTAG 选择，保持默认电平 |
| 5 | 烧录成功但 boot loop / 分区相关报错 / 应用起不来 | menuconfig Flash Size 与实片不符，分区表超容量或偏移越界 | `idf.py menuconfig` → Serial flasher config → Flash Size 对齐实片（4/8/16MB）；自定义分区表核对总大小；换板必查 |
| 6 | 按 datasheet 选的脚在板上无信号 | 模组只引出部分 GPIO；flash/PSRAM 专用脚不可用（classic GPIO6–11；S3 GPIO26–37 视模组；C3 GPIO11–17） | 一切以模组/开发板手册为准选脚，不按裸芯手册；先确认引出与默认上下拉 |

## 看门狗类（7–10）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 7 | 运行数秒后 `Task watchdog got triggered...`（TAG task_wdt），点名业务任务 | 长忙循环不让出 CPU；任务 WDT 默认 5s（CONFIG_ESP_TASK_WDT_TIMEOUT_S） | 循环内 `vTaskDelay(pdMS_TO_TICKS(10))` 或拆片处理；无须监视的任务不要 esp_task_wdt_add |
| 8 | `Guru Meditation Error: Core  0 panic'ed (Interrupt wdt timeout on CPU0)` | ISR 执行过长（默认约 300ms，CONFIG_ESP_INT_WDT_TIMEOUT_MS）或关中断太久 | ISR 只置标志/发队列，处理移到任务；ISR 及其常量加 IRAM_ATTR；缩短临界区 |
| 9 | Arduino loop() 长忙等后 TWDT 报 IDLE0，正在运行任务是 loopTask | loop() 不返回也不 delay，IDLE0 被饿死（task WDT 检查 IDLE 任务） | loop() 内加 delay(0)/yield()；重活移独立任务 |
| 10 | 高优先级任务常驻后 TWDT 报 IDLE0/IDLE1 | 优先级高于 0 的任务不让出，IDLE 饿死 | 同 7；勿用关 CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0/1 掩盖 |

## 中断类（11–15）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 11 | NVS/flash 写入（nvs_commit、分区擦写）瞬间偶发 `panic'ed (Cache disabled but cached memory region accessed)` | flash 擦写时 cache 禁用，ISR 代码/常量在 flash 中被取指 | ISR 及其调用的全部函数加 `IRAM_ATTR`；注册中断用 `ESP_INTR_FLAG_IRAM`；ISR 内不碰任何驻 flash 的 API |
| 12 | ISR 里 printf/ESP_LOG 后死机、丢日志或时序乱 | 日志走 UART 驱动＋flash 内字符串，非 ISR 安全且阻塞 | ISR 只记码值/写环形缓冲，由任务打印；必须现场输出用 ESP_DRAM_LOGE（仍阻塞，慎用） |
| 13 | ISR 里调 FreeRTOS/驱动 API 随机崩溃或断言 | 用了任务级 API（xQueueSend/vTaskDelay 等） | 全换 FromISR 版（xQueueSendFromISR…）；ISR 禁止任何阻塞调用 |
| 14 | ISR 触发后任务迟迟不执行、唤醒延迟不稳 | 漏 portYIELD_FROM_ISR，唤醒要等下个调度点 | 传 pxHigherPriorityTaskWoken，ISR 末尾 `if (woken) portYIELD_FROM_ISR();` |
| 15 | ISR 修改的标志任务里读不到/读到旧值 | 共享全局非 volatile，被编译器缓存进寄存器 | 标志声明 volatile；读改写/多字节共享量用 portENTER_CRITICAL 或原子操作；复杂数据走队列 |

## 外设类（16–21）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 16 | 开 WiFi 后 ADC2 通道读失败，关 WiFi 恢复 | classic/S3 的 ADC2 与 WiFi 射频共用，WiFi 启用期间被占 | 模拟采集一律用 ADC1：classic GPIO32–39、S3 GPIO1–10；C3 基本无此冲突（以 datasheet 为准） |
| 17 | LEDC 无输出或频率不对，代码看似没错 | freq × 2^duty_resolution > LEDC 时钟（APB 80MHz）时 ledc_timer_config 返回 ESP_ERR_INVALID_ARG，未检查则无声失败 | 检查返回值；上限速记：8bit→312.5kHz、10bit→78.1kHz、16bit→1.22kHz；降分辨率或降频 |
| 18 | I2C hang：调用超时/一直 BUSY，SDA 被从机拉低不放 | 主控复位时从机停在传输中途，等时钟继续输出 | 9 个时钟脉冲恢复＋手工 STOP（下方代码）；预防：4.7k 上拉、上电时序、驱动层超时自动恢复 |
| 19 | UART 收长数据偶发丢段/粘包 | rx ring buffer 太小或读不及时，溢出丢字节 | uart_driver_install 加大 rx_buffer（如 2048）；事件驱动及时 uart_read_bytes；会话切换前 uart_flush_input |
| 20 | classic GPIO34–39 当输出无电平，也配不了上下拉 | input-only 引脚，无内部上下拉（datasheet） | 只做输入；需要偏置用外部电阻；输出需求换脚 |
| 21 | S3/C3 程序复用 GPIO19/20（S3）、GPIO18/19（C3）后下载与串口日志消失 | 这四脚是 USB-JTAG/USB-Serial 默认功能脚 | 不要占用；确要复用需改外置 USB-UART 或 OTG，并记录恢复手段（按 BOOT 进下载模式） |

18 的总线恢复代码（两脚须先脱离 I2C 外设，总线有上拉）：

```c
void i2c_bus_recover(gpio_num_t scl, gpio_num_t sda) {
    gpio_set_direction(scl, GPIO_MODE_OUTPUT_OD);
    gpio_set_direction(sda, GPIO_MODE_INPUT);            // 释放 SDA 观察从机
    gpio_set_level(scl, 1);
    for (int i = 0; i < 9 && !gpio_get_level(sda); i++) {
        gpio_set_level(scl, 0); esp_rom_delay_us(5);     // 打时钟直至 SDA 释放
        gpio_set_level(scl, 1); esp_rom_delay_us(5);
    }
    gpio_set_direction(sda, GPIO_MODE_OUTPUT_OD);        // 手工 STOP：SCL 高时 SDA 拉低再释放
    gpio_set_level(sda, 0); esp_rom_delay_us(5);
    gpio_set_level(sda, 1);
}
```

## 内存类（22–25）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 22 | 任务跑一段后随机 Guru(Load/StoreProhibited) 或 `***ERROR*** A stack overflow in task xxx has been detected.`，STM32 迁移代码高发 | xTaskCreate 栈参数在 ESP-IDF 单位=字节；STM32 习惯按字（×4），实际只给了 1/4 | 直接写字节数（常规任务 4096 起）；uxTaskGetStackHighWaterMark 调优；勿关栈溢出检测 |
| 23 | 大缓冲 malloc/ps_malloc 返回 NULL，模组明明带 PSRAM | menuconfig 未启用 PSRAM 或未选 SPIRAM_USE_MALLOC | Component config → ESP PSRAM 启用并选用途；代码用 heap_caps_malloc(size, MALLOC_CAP_SPIRAM)（ps_malloc 为兼容别名）；启动日志确认 esp_psram: Found…MB 字样 |
| 24 | SPI/I2S/摄像头等 DMA 传输失败或数据花 | DMA 缓冲放 PSRAM（默认不可 DMA）或地址/大小不对齐 | heap_caps_malloc(size, MALLOC_CAP_DMA)；按外设要求对齐（常 4 字节倍数）；S3 个别外设经 EDMA 可入 PSRAM 但有约束，以官方文档为准 |
| 25 | esp_timer/esp_event/MQTT 事件回调里做耗时 IO 后：定时漂移、事件不派发、MQTT 假死 | 回调运行在 esp_timer 任务/事件循环/MQTT 客户端任务上下文，一阻全链卡死 | 回调只置标志/入队，业务放专用任务；回调保持 µs~ms 级 |

## 网络类（26–28）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 26 | esp_wifi_init 失败，日志/返回值含 0x1101（ESP_ERR_NVS_NOT_INITIALIZED） | 未先 nvs_flash_init，或自定义分区表缺 nvs 分区 | app_main 先 `nvs_flash_init()`；遇 NO_FREE_PAGES/NEW_VERSION_FOUND 则 nvs_flash_erase 后重试；分区表保留 data/nvs；esp_wifi_init 亦可能报 ESP_ERR_WIFI_NVS（0x3001），以 esp_err.h 为准 |
| 27 | 路由器断电/重启后设备永不重连，重启才恢复 | 未在 WIFI_EVENT_STA_DISCONNECTED 中重新连接 | 回调里 esp_wifi_connect()＋退避（重试上限后 stop、定时重启连接）；WIFI_EVENT_STA_START 里首次 connect；回调内不阻塞 |
| 28 | MQTT 长 payload 截断/收不到大消息 | esp-mqtt 默认 buffer_size 约 1024 字节，超长即截断/失败 | esp_mqtt_client_config_t 设 buffer.size / out_buffer.size ≥ 最大消息＋协议头余量 |

## 低功耗类（29–30）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 29 | 深睡醒来输出电平漂移、外设误动作（如继电器抖） | 深睡掉电后 IO 保持失效，未做 hold | 睡前 gpio_hold_en()；非 RTC 脚（S3/C3）再 gpio_deep_sleep_hold_en()；唤醒后 gpio_hold_dis() 再操作。详见 power-and-sleep.md |
| 30 | 深睡被随机唤醒/唤醒统计异常 | 唤醒脚悬空受干扰；深睡下内部上下拉不可靠 | 唤醒脚加外部 10k 级上/下拉；核对是否 RTC GPIO；用 esp_sleep_get_wakeup_cause() 统计验证 |

## 工具链类（31–35）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 31 | 换 target（esp32↔esp32s3↔esp32c3）后大量诡异编译/配置错误 | sdkconfig/build 残留旧 target 配置 | `idf.py fullclean` 后 `idf.py set-target <target>` 重新生成；勿跨 target 复制 sdkconfig |
| 32 | 烧录报串口打不开 / PermissionError(13, 拒绝访问) | idf.py monitor 或串口助手占用 COM 口 | monitor 内 Ctrl+] 退出再 flash；或 `idf.py flash monitor` 一条龙；排查占用进程 |
| 33 | Windows 构建随机失败/工具链报路径错 | 工程或 IDF 路径含中文/空格（用户名含中文同理） | 全链路径纯 ASCII 无空格（如 C:\esp\…）；用户名含中文时工程移出用户目录 |
| 34 | arduino-esp32 2.x→3.x 升级后 ledcSetup/ledcAttachPin「未定义」编译失败 | 3.x 重写 LEDC API，channel 概念隐藏 | `ledcAttach(pin, freq, res)` 替代 ledcSetup＋ledcAttachPin；`ledcWrite(pin, duty)`；`ledcDetach(pin)`；其余差异对照 3.x API 手册 |
| 35 | Keil/MDK 迁来源码注释乱码、字符串长度异常 | 文件编码 GBK，工具链按 UTF-8 | 全部转 UTF-8；新文件统一 UTF-8；中文字面量按 3 字节/字参与 sizeof |

## 实战项目类（36–53）

源自三个**已上板工程**的源码审计（症状标签：【BLE HID】=Keybrick C3 BLE 键盘；【飞控】=Flix 四旋翼；【IoT 网关】=yihong-iot MQTT 网关），模式详解分别见 ble-hid-arduino.md / realtime-control.md / iot-gateway-patterns.md。条目来自已运行项目的真实故障记录；未经本机复现，跨平台/跨版本表现仍需按条目内建议实测。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 36 | 【BLE HID】BLE 键盘断连（手机切走/超时）后手机再也搜不到设备 | onDisconnect 回调里没重启广播，从机只广播一次 | onDisconnect 里 `BLEDevice::getAdvertising()->start();`（经典库与 NimBLE 同理）；断连事件是常态不是异常，必须处理 |
| 37 | 【BLE HID】HID 报告在这台手机生效、换一台失灵 | 报告描述符 REPORT_ID 约定与系统栈实现不一致 | 描述符/发送两侧统一"键值不带 REPORT_ID 前缀"（keyArray[0]=modifier 起）；跨 iOS/Android/Windows 实测后再定稿 |
| 38 | 【BLE HID】电子节拍器/周期任务越跑越偏，BPM 实测偏低 | 每拍用 `delay(beatMs)` 对齐：执行耗时叠加进周期 | 增量法：`nextBeat += beatMs;` 循环条件 `while (millis() - lastBeat < beatMs) yield();` 或到点即发，误差不累积 |
| 39 | 【BLE HID】按键按一下、对端连发多次 | 双读去抖只判电平稳定，没判状态沿（按下→抬起各触发一次逻辑） | shouldSend 一次性标志：按下沿置位、发送后清；isReleased 检测抬起沿才允许下次 |
| 40 | 【BLE HID】普通键正常、媒体键（播放/音量）无效 | Consumer Control 用法被塞进键盘报告数组 | 媒体键走独立 Consumer 报告（独立 REPORT_ID 的 16bit 位图描述符），与键盘报告分开发送 |
| 41 | 【BLE HID】GPIO 模拟 I2C 驱动 OLED 花屏/半屏 | 软 I2C 无 ACK 检查、无开漏配置，时序错也当成功 | 换硬件 Wire（C3: GPIO8=SDA/GPIO9=SCL 默认），或软 I2C 开漏+每字节查 ACK，失败重试 |
| 42 | 【BLE HID】长按切换输入模式后，原模式按键持续"卡住" | 切走时没发全零报告，对端仍持有旧按下状态 | 任何模式切换/休眠前先发全零空报告（release all），再停发送 |
| 43 | 【飞控】换 IMU 芯片或改安装朝向后，姿态疯转/一发油门就翻 | 机体坐标系映射 rotateIMU 是单行硬编码，换硬件后轴/符号全错 | 按新 IMU 的轴映射改那一行；物理验证：平放 z≈+1g、机头抬起 pitch 符合定义，再上桨 |
| 44 | 【飞控】飞行中调参（写 NVS/Preferences）瞬间姿态抽动、掉高 | NVS 写是毫秒级阻塞 flash 操作，卡进 1kHz 控制环丢拍 | 飞行状态（motorsActive()）禁写 NVS，参数落地统一 disarm 后或地面保存；脏标志 1Hz 批量化 |
| 45 | 【飞控】电机启动/加油门瞬间整机复位循环，日志报 brownout | MOSFET 浪涌拉垮电源触发欠压复位 | 硬件优先：电源余量、加粗地线、母线电容；软件最后手段 `REG_CLR_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_ENA)` 关欠压复位（掩盖不解决，仅隔离测试用） |
| 46 | 【飞控】testMotor/单电机测试时转时不转 | LEDC 改占空撞上当前周期未结束，占空丢失（arduino-esp32 #5306） | 改写占空前 `delay(50)` 等当前 PWM 周期走完；或用 ESP32 LEDC 硬件的 duty 更新语义（见 #34 的 3.x API） |
| 47 | 【飞控】地面站（QGC）连不上飞控 WiFi | AP+UDP 14550 用广播包，部分 GCS 不发首包触发不了下行 | 连 Drone_WiFi 后在 QCG 手动指定/触发通信（先发包改单播对端 IP），或固件侧定期广播心跳 |
| 48 | 【飞控】悬停缓慢漂移，越飞越歪 | 空中仍在用加计校正姿态：加计含运动加速度，偏置被错误吸收 | landed 判定（!motorsActive() 且 \|accNorm−1g\|<10%）才校正；起飞前静止 ≥2s 完成陀螺 bias 校准 |
| 49 | 【IoT 网关】PubSubClient 发大 JSON（>256B）总失败，publish 返回 0 | PubSubClient 默认缓冲 256B，超长 MQTT 包被静默截断/拒发 | `setBufferSize(≥最大消息+512B)`；发送前长度预检，超限拒发并记录，勿截断硬发 |
| 50 | 【IoT 网关】MQTT connected()==true 但服务器没收到（publish 假成功） | TCP 半开（服务器重启/NAT 超时无 RST），QoS0 无确认 | 发布防御四连：发前查连接+就地重连、长度预检、失败重连重发一次、置脏标志下轮复查；不丢数据靠应用层 guid 回执 |
| 51 | 【IoT 网关】设备连续运行 49.7 天后心跳/TTL 全错乱 | millis() 回绕；绝对值比较或 millis()/1000 存的 TTL 跨回绕点全错 | 周期判断一律无符号差值 `(now - last) >= period`；持久化 TTL 用 esp_timer_get_time()/RTC，不用 millis |
| 52 | 【IoT 网关】服务器拒收深嵌套多空字段 JSON，纯文本却能发 | 对端模型校验严格：空字符串字段解析失败、嵌套层级超出模型 | 上行降级平面格式；空字段发 `null` 不发 `""`（时间戳类尤其）；发出前 deserializeJson 回读自验 |
| 53 | 【IoT 网关】域名解析正常、浏览器能开，MQTT 就是连不上 | DNS 缓存陈旧/解析超时指向错误 IP | WiFi.hostByName 预解析→WiFiClient TCP 探活→探活成功即 `setServer(IP, port)` 绕过域名，故障段定位进日志 |

## 传感器类（54–61）

源自 heart-rate-spo2-master（MAX30102，已上板工程；寄存器语义以 MAX30102 datasheet 为准）。

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 54 | 【MAX30102】MicroPython 固件 + PC 算法，指位 Fin 恒 0、永远"未检测到手指" | init.py:581-583 读数 `>>pulse_width`（411µs 时=3）使数值÷8，低于 PC 端 ir>150000 阈值（该阈值基于 SparkFun 18bit 不移位量纲） | 删移位保持 18bit 原始量纲，或按固件区分阈值；跨固件对接先对同一手指采一组数对量纲 |
| 55 | 【MAX30102】I2C 无 ACK / Arduino 循环打印 "Sensor connection failed!" | 接线错（README 两套 ESP32 引脚：Arduino=C3 的 IO8/IO9，MPY=IO10/IO6）/无上拉/地址非 0x57；且代码不自检：check_part_id 无人调用、scan() 结果被丢弃（init.py:526-529） | 初始化前 `scan()` 应见 87(0x57) 再继续；核对上拉（以模块原理图为准）；失败即停并报错，勿带病运行 |
| 56 | 【MAX30102】波形断续、脉冲"缺拍" | MPY check() 每次只读 1 样本 + OVF(0x05) 从不读 + rollover 覆盖 + 软件队列仅 4 深（init.py:156,684），主循环稍慢即溢出丢样 | 批量读完 WR−RD 全部样本、每轮检查 OVF 计数、加大软件队列；50Hz 有效率下主循环节拍必须 <20ms |
| 57 | 【MAX30102】BPM 数值乱跳、偶发尖峰 | AMPD 找峰作用于未滤波 red 序列（运动伪影直接成峰），BPM 用单个 RR 间期折算（Max_30102.py:72-82），10 点均值压不住野值 | 滤波后找峰（或 AMPD 后加间期合理性窗），BPM 用最近 N 个 RR 中值而非单个；显示层再做平滑 |
| 58 | 【MAX30102】SpO2 周期性跳 0 | AC/DC 取窗口 max/min 对窗长和伪影敏感，出界(>100/<0)整体置 0（Max_30102.py:58-65） | 仅 Fin=1 且 data_valid 才计算；逐样本剔野（与中值偏离>阈值丢帧）；窗长覆盖 ≥2 个完整搏动 |
| 59 | 【MAX30102】自改采样率/平均后心率血氧全乱 | PC 端窗口固定 120 样本、滤波 Wn=0.1/0.3 是相对 Nyquist 的归一化频率，隐含"有效 50Hz"假设 | 固件保持 50Hz 有效输出（sps/avg 不变），或 PC 按 time 戳重采样并同步改 Wn 与窗口 |
| 60 | 【MAX30102】SpO2 大幅偏离而心率正常 | 样本字节序 LED1(Red)3B+LED2(IR)3B 接反使 R2 分子分母互换（Max_30102.py:62）；init.py:42-43 注释把 0x0C/0x0D 红外标反更易误导 | 以 datasheet 核对 0x0C=Red、0x0D=IR；实测区分：红光手指吸收随搏动更明显/遮挡单 LED 验证通道 |
| 61 | 【MAX30102】噪声大、数据漂、模块发热 | 亮度 150≈29mA/通道、双 LED 峰值叠加，供电与去耦不足（仓库未写供电规范） | 3.3V 稳压+去耦以模块原理图为准；先降亮度（如 60）验证噪声是否随电流下降；连续应用加采集间隔降功耗 |

## 语音 AI 类（62–71）

源自 xiaozhi-esp32（已上板工程；上游 github.com/78/xiaozhi-esp32）。

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 62 | 【语音 AI】xiaozhi-esp32 编不过 / 组件 ABI 报错，或 C3 上 v6.1 tag 固件 Wi-Fi 初始化失败 | 项目强制 IDF≥6.0.1（推荐 release/v6.1 分支，不支持 5.x）；v6.1 发布标签在 C3 有 Wi-Fi init 失败（官方 #2344） | 装 IDF 6.x 用分支不用 tag；切 SDK 后 `git submodule update --init --recursive` + 重新 export + `idf.py fullclean`（README_zh.md:17,121） |
| 63 | 【语音 AI】4MB flash 设备永远收不到 OTA 更新 | partitions/v2/4m.csv 只有 factory 无 ota_0/1；MarkCurrentVersionValid 跳过 factory 分区 | 换 ≥8MB flash 或 v1 分区表；或引导手动烧录（partitions/v2/4m.csv:6；ota.cc:260-265） |
| 64 | 【语音 AI】无 PSRAM 板唤醒词无效 / 说话卡死 | USE_AUDIO_PROCESSOR depends SPIRAM；AFE 内存/任务栈/唤醒 64KB 环缓全放 PSRAM | 确认板型带 PSRAM（S3/P4/S31 走 AFE）；ESP32/C3 走 LiteAudioEngine 独立 WakeNet（Kconfig.projbuild:1059-1066） |
| 65 | 【语音 AI】对话中途卡死无声，重启才恢复 | 音频发送失败未清空剩余队列，Opus 任务阻塞等满队列→整条输入管线死锁 | 发送路径失败必须清队列（上游 application.cc:253-258 已修）；自定义发送路径同样处理 |
| 66 | 【语音 AI】烧错板型：无声 / 引脚错乱 / OTA 身份混乱 | 每板 config.h 硬编码 I2S/PA 引脚；改已有板引脚破坏 OTA 板身份 | 板目录逐字核对再烧；新硬件复制新板目录+DECLARE_BOARD，勿改已有板（AGENTS.md:29） |
| 67 | 【语音 AI】开着音箱说话唤醒不了 / 自打断 | 无 AEC 硬件时唤醒词被自家喇叭淹没；device AEC 仅白名单板可选；R 通道必须是播放参考而非第二麦 | 用 BOX 系列等带参考通道硬件（AUDIO_INPUT_REFERENCE）；或关播放再唤醒；AEC 关时用 AutoStop 听音模式（Kconfig.projbuild:1068-1081） |
| 68 | 【语音 AI】WebSocket 一直连不上，日志 "No websocket section found" | ws/mqtt 配置由 OTA 接口 HTTP 响应下发并写 NVS；CONFIG_OTA_URL 错或网络不通→无配置→回退默认 MQTT | 核对 ota_url 与 Device-Id/Token；抓 OTA 响应确认 websocket 节点存在（ota.cc:56-63,180-199） |
| 69 | 【语音 AI】device AEC 与 server AEC 同开直接编译失败 | 二者互斥，`#error` 显式拦截 | 只开一个；AEC 能力在 hello 的 features.aec 里协商（application.cc:28-36） |
| 70 | 【语音 AI】4G 板（ML307）收事件再发数据死机/无响应 | 模组 AT 事件任务上下文内禁止再发起发送 | 回调一律 Schedule() 到主任务再发送；心跳靠 MQTT keepalive 不自造（websocket_protocol.cc:161-170） |
| 71 | 【语音 AI】MCP 工具调用偶发不响应 | 工具数量超限/未按服务端 prompt cache 建议前置排列，被服务器静默丢弃 | 控制工具数量、常用工具前置；注册工具与 GetDeviceStatusJson 状态对齐（mcp_server.cc:29-31） |

## 电机控制类（72–81）

源自 Skythinker foc-wheel-legged-robot（已上板工程；上游 gitee.com/skythinker/foc-wheel-legged-robot；证据为 esp32-controller\software\src\main.cpp 行号）。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 72 | 【电机】总线一次异常（短路/强干扰）后 CAN 节点永久静默，重启才恢复 | `alerts_enabled=TWAI_ALERT_NONE` 且从不检查 bus_off，无 `twai_initiate_recovery()` | 启用 TWAI_ALERT_BUS_OFF 告警，触发后 recovery+`twai_start()`；周期查 `twai_get_status_info().state`（main.cpp:280-286,301） |
| 73 | 【电机】蓝牙遥控断连后机器人沿最后指令继续行驶 | onDisconnect 只重启广播，无指令超时；speedCmd/yawSpeedCmd 保持旧值 | 断连回调或 >500ms 无 0xAA 帧即清零速度/偏航指令（main.cpp:764-768） |
| 74 | 【电机】每换一块板都要手改源码重烧 | IMU 零偏 6 个 int 硬编码（accel −668/−1632/998，gyro 283/80/42），标定函数被注释 | 上电静止自校准（均值法）+ NVS 存储零偏（main.cpp:392-400） |
| 75 | 【电机】角速度读数整体偏小约 8 倍/姿态发散 | 按 16.4 LSB/(°/s)（±2000dps）换算但未调 `setFullScaleGyroRange`，库默认可能是 ±250dps | 初始化显式设 `MPU6050_GYRO_FS_2000`；换算系数必须与实际量程档一致（main.cpp:346-348） |
| 76 | 【电机】跌倒后保护分支卡死不退出、也不复位 | `while(PROTECT_CONDITION)` 无超时，IMU/CAN 停更则条件永真；esp_task_wdt 只 include 从未注册 | 保护等待加超时与退出路径；电机类任务显式 `esp_task_wdt_add()`（main.cpp:671-676,18） |
| 77 | 【电机】控制环偶发用到半更新的传感器数据，抖动无规律 | motor.angle/speed、imuData 由 CAN/IMU 任务写、Ctrl_Task 读，无临界区/锁 | portENTER_CRITICAL 快照或序列锁；多字节共享量禁止裸读写（main.cpp:195-196 vs 553-556） |
| 78 | 【电机】电池低压后输出突然变弱/行为突变 | `sourceVoltage<8V` 判无效后置假值 12 → motorOutRatio 按满电算偏小 | 低压直接停机报警，不伪造电压值（main.cpp:858-860） |
| 79 | 【电机】端到端控制延迟抖动大，最坏 >6ms | 指令 2ms 任务 + 反馈 2ms 轮询 + 250Hz 控制环三级串行叠加 | 反馈进控制环内联读取，或提 CAN 接收任务优先级（main.cpp:239,286,699） |
| 80 | 【电机】BLE 调试帧可任意读写设备 RAM，量产有安全隐患 | 0xDB Linkscope 帧仅地址段限制无鉴权；GATT 无加密未配对（SMP 使能但没用） | 量产关闭调试特征；或白名单地址段+强制配对加密（main.cpp:800-803；debug.c:11） |
| 81 | 【电机】上电后约 5s 无响应，用户误以为已就绪 | setup() 先 `vTaskDelay(5000)` 黑窗，期间无 CAN 输出 | 上电用 LED 明示状态；延时期间打日志（main.cpp:878-880） |

## 量产手册类（82–93）

源自用户提供的《ESP32 软件开发避坑手册（量产级）》文档（文档沉淀，未上板实测；详见 [production-readiness.md](production-readiness.md)）。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 82 | 【量产】总空闲内存够却 malloc 失败（如空闲 120KB 申请 32KB 失败）；运行越久越容易失败 | 内存碎片：最大连续块不足（largest_free_block 仅 8KB 级）；频繁 JSON/分包/OTA 缓冲反复申请释放 | 固定缓冲静态分配/内存池；减少运行时创建任务与队列；定时打印 heap_caps_get_info() 盯 largest_free_block |
| 83 | 链接错误 `section '.iram0.text' will not fit in region 'iram0_0_seg'` | 滥加 IRAM_ATTR，IRAM 容量有限 | 只给 ISR 与 flash 写期间运行的代码加；其余靠 cache 命中 |
| 84 | 随机重启/无关任务挂掉/业务数据错乱，找不到原因 | 栈溢出静默踩相邻任务栈/全局/队列；未开检测未测水位 | configCHECK_FOR_STACK_OVERFLOW=2；定期 uxTaskGetStackHighWaterMark，水位 <200 字即加栈 |
| 85 | 解析深层 JSON/遍历目录时崩溃 | 任务栈仅几 KB，递归吃光 | 改迭代或队列化，任务内禁止递归 |
| 86 | WiFi 显示 connected 但 MQTT/云端不通 | 假连接：AP 断流/路由器死机/DNS 失败/服务器不可达 | 双层保活：WiFi 事件+RSSI+重传率 + MQTT keepalive(≈30s)/TCP 心跳 |
| 87 | 弱网下越忙越连不上，最终雪崩 | 无限流：心跳堆积、高频数据猛发 | 心跳未应答不发下一个；数据 QoS0/控制 QoS1；RSSI<−85dBm 降频；OTA 期间限业务报文 |
| 88 | 写 NVS 越用越慢/报 ESP_ERR_NVS_NO_FREE_PAGES | 每次变化即写：磨损+页耗尽 | 变更后延迟写入；写前校验；重要参数加 CRC16 |
| 89 | 启动慢；深睡唤醒后 WiFi 连不上/不稳 | PHY 校准数据未存 NVS，每次启动完整校准 | menuconfig 开启 PHY 校准数据存储到 NVS |
| 90 | 定时唤醒周期越跑漂移越大（可达 ±10%） | 用内部 RC 振荡器做低速时钟 | 电池节点加外部 32.768kHz 晶振 |
| 91 | 弱网 OTA 反复从头下载，永远升不完 | 无断点续传 | 已下载偏移量存 NVS，重连后续传 |
| 92 | 量产设备串口拖慢系统/时序异常；printf 栈溢出 | Debug 日志全开；printf/sprintf 吃栈 | 量产只留 W/E 级，调试日志用 #if CONFIG_LOG_DEFAULT_LEVEL 包裹；启用 Newlib Nano formatting |
| 93 | OTA 途中被配网/重连/复位打断变砖 | 无升级互斥锁 | OTA 中禁配网/频繁重连/系统复位；配网重连期间也禁启动 OTA |

## 教育机器人 / Mind+ 类（94–101）

源自用户提供的已上板工程（瑞龙 ESP32 物联网机器人 Mind+ 扩展库 V0.0.2，含编译产物实证；详见 [mindplus-robot-ext.md](mindplus-robot-ext.md)）。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 94 | 【电机】直流电机啸叫、低速扭矩抖动、H 桥发热大 | MCPWM 初始化 `frequency = 50`（源码注释写 500Hz 也不对）——50Hz 是舵机频率；直流电机 H 桥应 10–20kHz | 频率改 10k–20kHz（超声频段）；50Hz 只留给舵机；代码注释与实现矛盾时以示波器/实测为准 |
| 95 | 【电机】期望「停转滑行」却猛刹一顿顿走，或反之 | `Motor_Speed(0)` 双输出恒高——多数 H 桥双输入同电平=刹车（brake），不是滑行（coast） | 按驱动芯片手册确认双高语义；要滑行用双低（`mcpwm_set_signal_low` 双侧）或 A 路 PWM 归零 |
| 96 | 【FPV】`FpvReadByte()` 偶发返回随机值 | 传入 index>8 时函数无默认返回值（C++ UB）；图形块枚举掩盖了非法值可能 | 补 `default: return 0;`；调用侧对枚举值域封口 |
| 97 | 【FPV】自写校验和照抄 `a^b^c^d^e&0xff` 移植到 uint16 后校验总错 | 运算符优先级：`&` 高于 `^`，只有最后一项被掩码（字节场景碰巧无害） | 加括号写成 `(a^b^c^d^e)&0xff`；位运算混合必加括号 |
| 98 | 【FPV】一键起飞/降落命令偶尔丢失 | 命令为脉冲语义：遥控器先置 1 约 1 秒后自动置 0；轮询环阻塞（delay/长任务）超过脉冲窗即错过 | 控制环单圈耗时 <200ms；命令沿检测（1→0/0→1）而不是电平轮询；严禁在 forever/loop 里长 delay |
| 99 | 【Mind+】旧案例 .mp 打开编译后新功能（无头模式/陀螺仪校正）读不到 | .mp 案例文件内嵌**当时版本**的扩展库副本（实测：综合测试.mp 内嵌 V0.0.1 旧库，V0.0.2 才补齐 bit4/bit7 分支）；升级已装扩展不回填旧案例 | 新建案例重新拖积木（引用最新库）；或解包 .mp 替换内嵌扩展目录；发版时在发布日志写明 API 变更 |
| 100 | 【Mind+】同一编码器拖了两个不同模式积木（如单边沿读数+全周期清零），行为只按其中一个走 | 生成器 `addSetup` 按固定键去重：键名硬编码 `attachSingleEdge` 不含实际模式，后注册的 setup 行覆盖先注册的 | 同一对象只用一种模式积木；写扩展时把模式编进键名（`encoder_${pin}_${mode}`）；生成后核对 .ino 的 setup() |
| 101 | 【电机/编码器】Arduino core 3.x 或升 IDF 5.2+ 后编译出 deprecation 警告，或新工程找不到 `mcpwm_init` | legacy 驱动（`driver/mcpwm.h` 的 `mcpwm_init/mcpwm_set_duty` 系、`driver/pcnt.h`）在 IDF 5.2+ 标记弃用，新 API 是 `driver/mcpwm_pwm.h`（mcpwm_new_timer/operator/comparator）与 `driver/pcnt_new.h` | 存量库锁版本继续用 legacy（仍可编译）；新写代码按官方迁移指南用新 API；以官方文档为准 |

## MicroPython 商用工程类（102–115）

源自用户提供的已上板商用工程（env-controller v1.5.1-beta，ESP32-S3 N16R8 自编译 MicroPython v1.28；详见 [micropython-env-controller.md](micropython-env-controller.md)）。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 102 | 【MP/Web】microdot 保存大配置（>16KB）静默失败，小配置正常 | microdot 默认 `Request.max_content_length=16*1024`，超限直接拒收 body 无业务报错 | 启动时设 `Request.max_content_length = 4*1024*1024`；上传接口自检 content-length 并显式报错 |
| 103 | 【MP/固件】整机"卡死"无任何异常日志，网络全断 | MicroPython v1.28 `IOQueue.wait_io_event` 对失效 socket 抛 OSError(EIO) 未捕获，崩溃整个 asyncio 事件循环 | 启动期 monkey-patch IOQueue：重建 poll、只剔失效 fd（app_main.py:32-100 打法）；升级固件关注官方修复 |
| 104 | 【MP/GC】Web/控制周期性卡顿数百 ms | 堆耗尽才触发一次大 GC（曾一次释放 7MB）；SD 同步写阻塞 100ms+；`gc.mem_free/alloc` 单次约 15ms 频繁调用 | `gc.threshold(4*1024*1024)` 小步 GC；心跳/请求路径不落 SD、不 `gc.collect`；内存统计 30s 采一次 |
| 105 | 【MP/W5500】首次 web 请求后串口刷 `spi transmit failed`，以太网断 | SPI 的 Python 包装对象被 GC 析构，把已交 esp_eth 接管的外设 deinit 了 | 模块级引用（如 `_spi_keep`）钉住底层对象；外设移交 C/底层后 Python 句柄只增引用不析构 |
| 106 | 【MP/RS485】快速从站响应整帧被吞/总线偶死锁 | DE 方向保持用 Python 粗估 +10ms 过长；asyncio 短睡眠被事件循环吞掉，DE 卡高占线 | 时序敏感路径下沉 C 扩展（`de_write` 硬件判定发完立即释放）；Python 路径用同步 `sleep_ms` 不进事件循环 |
| 107 | 【MP/RS485】9600 波特长帧 CRC 失败，只收到 20–21 字节 | 帧空闲判定 10ms < 29 字节帧传约 30ms，且 asyncio 事件循环在字节间插空，提前判帧结束 | FRAME_IDLE_MS 提到 30；按波特率×最长帧算空闲阈值；收完再校验长度+CRC |
| 108 | 【MP/Modbus】写已执行但主机报"从站无响应" | 总线残留污染回显/从站无回显，把回显帧或静默当响应判定 | 写响应窗口 0.8s + 无回显判成功 + 四层回显匹配（modbus.py:150-215 打法） |
| 109 | 【MP/Modbus-TCP】压测（~25 连接/s 连断风暴）整机冻结 | `asyncio.start_server` 每连接一任务，任务创建/销毁风暴冻结事件循环 | 单任务轮询非阻塞 socket；连接数上限（6）+ 空闲超时（15s）+ 缓冲上限（2KB）防恶意 length |
| 110 | 【MP/Modbus】u16 寄存器读数 40000 显示成 -25536 | 解析层对所有 datatype 统一做符号扩展 | datatype 区分：仅 s16/s32/int 符号扩展，u16/u32 不动（sensor_service.py:113-122） |
| 111 | 【MP/asyncio】联动规则里 `await asyncio.sleep(0.01)` 后的动作偶发永不执行 | MicroPython asyncio.sleep 小数秒内部共享单例生成器，并发等待被吞 | 自写 `_sleep_ms`：`ticks_ms` 硬超时 + `sleep(0)` 纯 yield（全项目统一用法） |
| 112 | 【MP/架构】服务读不到板载输入、latest_data 时有时无 | 其他模块 `import main` 重执行 main.py，状态被重置 | main.py 仅 import app_main 并注册 `_sys.modules['main']` 别名；共享态走中间件模块 latest_data |
| 113 | 【MP/OTA】升级"成功"但行为没变，且源码泄露在 flash | import 优先 `.py`：新 `.mpy` 落地后旧 `.py` 仍被加载 | .mpy 覆盖时把同名 .py 同步改 `.upg.bak`；升级校验拒绝明文 .py 入包 |
| 114 | 【MP/MQTT】带用户名密码连 broker 被 RST；断线后永不重连 | umqtt.simple 的 user/password CONNECT 编码 bug；`is_connected()` 曾恒 True 假死 | 自写极简 3.1.1 客户端（分片≤128B）；主循环 0.5s 检测 + 30s 静默重连重订阅 |
| 115 | 【MP/OTA】升级包损坏/被篡改/版本不符直接变砖 | 无校验链：垃圾 tar、明文 .py、.mpy 字节码版本与固件不符都能落盘 | tar 头 checksum + 截断检测 + 路径白名单 + 拒明文 .py + .mpy 头 0x4D 且版本绑定固件 + 旧文件 .bak + 失败自动回滚 |

## Modbus / RS-485 主机类（116–124）

源自用户提供的已上板工程（tiny485-mbrtu v1.0 / ZeroOneLab / MIT，STM32F103ZE+MAX485 已上板运行；ESP32 移植建议为文档新写、未经编译验证；详见 [modbus-rtu-485.md](modbus-rtu-485.md)）。

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 116 | 【Modbus】主机每次事务都耗满整个超时（响应 10ms 到也等满 1000ms），CPU 空转；RTOS 下饿死同核低优先级任务甚至触发 TWDT | `mbrtu_wait_data` 定长忙等：`while (now-start < timeout);` 烧满才查一次接收计数，且循环无 yield | 等待循环内轮询 recv_cnt 增长并重置起点（字节间隔判帧完），配合 `vTaskDelay(1)` 让出（见 modbus-rtu-485.md §4.4 改造版） |
| 117 | 【Modbus】读 >29 个寄存器必失败，报 TIMEOUT 而非长度错误 | 0x03 响应=5+2N 字节；64B 缓冲在 `(cnt+len)>=SIZE` 即整包丢弃清零 → cnt==0 → 误判超时；64B 上限仅对应 29 寄存器（库 README 写"≤123"与规范值 125、缓冲上限均不符） | 缓冲按最大响应预算：`SIZE ≥ 5+2N+2`；读数量与 MBRTU_RECV_BUF_SIZE 一起定 |
| 118 | 【Modbus】slave=0 / quantity=0 / 超范围参数照发不误，直到从机回异常帧才暴露 | 错误码枚举定义了 MBRTU_ERR_PARAM，但核心层从不校验入参、从不返回它（文档承诺≠实现） | 调用前自校验：1≤slave≤247（0 仅广播写）、1≤quantity≤125（0x03/04）或 ≤123（0x10） |
| 119 | 【Modbus】传入 lun≥MBRTU_NUM 后内存被静默写坏、随机崩溃 | `mbrtu_recv_handler`/build 系列对 lun 无边界检查，直接索引静态数组越界 | 端口层 switch-default 拦截非法 LUN；或核心层入口加 `lun < MBRTU_NUM` 检查 |
| 120 | 【RS485】IDF 移植后从机偶发收到被截尾的请求帧（末 1–2 字节丢/CRC 错） | `uart_write_bytes` 写入 TX 缓冲即返回，紧跟的 `gpio_set_level(DE,0)` 把尚未上线的帧掐断（STM32 `HAL_UART_Transmit` 阻塞语义掩盖了此问题） | 拉低 DE 前必须 `uart_wait_tx_done`（Arduino 轨用 `MB.flush()`，arduino-esp32 语义为等发送完成）；或改 `UART_MODE_RS485_HALF_DUPLEX` 硬件方向控制 |
| 121 | 【Modbus】长帧/强干扰后连续多轮 CRC 错，之后又自愈 | 接收溢出处理仅清 cnt=0，后续字节照常追加——把当前帧后半段当成新帧起点，重组出错位帧 | 溢出后进丢弃模式：记时间戳，总线静默 >帧间隔（9600 下 ≥30ms）才恢复接收 |
| 122 | 【Modbus】用地址 0 广播写单寄存器（合法用法）却等满超时后报错 | 从机对广播不回响应，主机 wait_data 必超时 | `slave==0` 时跳过等待直接返回；或协议层明确禁用广播 |
| 123 | 【RS485】发送期间自己的接收缓冲出现"幻影数据"，解析永远失败 | DE 与 /RE 分开接（/RE 常使能）时收发器回显自身发送；DE+/RE 绑一起接法则无回显——同一库不同接线行为不同 | 接线统一由一脚控制 DE+/RE；软件侧发送前清接收缓冲（源工程"发送前清缓冲"正是此意）；IDF 硬件 RS485 模式的回显行为以官方文档与实测为准 |
| 124 | 【RS485】每次发送前固定延时 1ms，高频轮询吞吐折损 10%+ | 端口函数 DE 建立延时写死 `HAL_Delay(1)`：收发器建立只需 µs 级；8B 帧@9600 共 8.3ms，1ms 占比约 12% | 改 `delayMicroseconds(10)` 量级；根治用 UART 硬件 RS485 模式（零软件延时、零手动切换） |

## BLE/微信小程序外设类（125–138）

| # | 症状 | 根因 | 修法 |
|---|------|------|------|
| 125 | 【BLE】手机断开（超距/小程序杀后台）后再也搜不到设备，只能断电重启 | GATT 服务端未注册 `BLEServerCallbacks::onDisconnect`，断连后不重启广播，设备永久不可发现 | onDisconnect 内 `BLEDevice::startAdvertising()`（见 ble-weapp-morse-trainer.md §4 修复版） |
| 126 | 【BLE】下发播放长文本后数秒内蓝牙完全无响应，期间命令全部丢失 | `ply:` 命令在 onWrite 回调里直接调阻塞版 `play_code`（逐字符 delay），把 Bluedroid 回调任务卡死 | 回调内只置标志/入队，播放交给独立任务（源工程后来的 `plc:` 另核播放即此意图，旧 `ply:` 未删） |
| 127 | 【GPIO】手动电键未按下却乱触发；把手动键改到别的引脚后完全失效 | `pinMode(pin_key, INPUT_PULLUP)` 被注释掉，GPIO4 的上拉是自动键 `pin_key_da` 初始化的副作用，换引脚后悬空 | 每个用到的输入脚显式初始化自己的 pinMode；不依赖其他模块的初始化顺序 |
| 128 | 【GPIO】按住自动键 di 桩再上电/复位，设备进下载模式、烧录失败 | di 桩接 GPIO0（BOOT strapping）：低电平启动进 bootloader；按键是"拉低"器件，天然冲突 | 按键避开 GPIO0/2/12/15（strapping）；已占用的须保证上电瞬间不被按住并在文档标注 |
| 129 | 【触摸】未触摸时偶发误判按下（读值突降为 0）；换 S3/C3 后 touchRead 编译报错或恒 0 | 经典 ESP32 touchRead 偶发返回 0（源码注释"原因待查"）；S3/C3 无触摸外设；core 2.x 起返回值改经校准、阈值跨版本不可比 | 读值为 0 时二次读防御；跨芯片改 GPIO 按键或 TTP223 类电容芯片；阈值按所用 core 版本实测标定 |
| 130 | 【并发】快速连发 BLE 消息时内容错乱、播放任务串码 | `var_ble_msg`/`var_code_list` 全局 String 无锁：新一次 ble_send_core/新 plc 命令在旧任务读取前覆盖共享缓冲 | 共享消息改队列（StreamSend/FreertosQueue）或局部拷贝后传参；至少加"上一任务未完成不再创建"哨兵 |
| 131 | 【C++】把某处调用改成一参 `ble_send(msg)` 后链接报 undefined reference | 头部声明 `void ble_send(String)` 与定义 `void ble_send(String,String)` 签名漂移，单参版从未定义，长期靠"恰好无人调用"侥幸 | 删未用声明或补定义；同名不同参的重载靠调用点兜底不是设计（见 ble-weapp-morse-trainer.md §3） |
| 132 | 【NVS】设置面板连点几轮后 NVS 写入次数暴涨、寿命无谓消耗 | Arduino EEPROM 模拟层每次 `commit()` 都是整块擦写 NVS 分区；源工程每改一项参数就 write×5+commit 一次，14 项全存=14 次全量 | 改 `Preferences` 键值级 NVS（磨损均衡、按需写入）；或攒批后一次 commit |
| 133 | 【存储】参数 >99999 被静默截断；float 参数存取精度全靠运气 | 定长 5 字符右对齐零填充落盘：`String(1800)` 恰 4 位安全，`String(3.0)="3.00"` 两位小数恰好装下纯属范围运气 | 存储层用二进制定宽（int32/float 原生 4B）或 JSON；文本定长必须先验宽度再落盘 |
| 134 | 【CW】改"字母间隔时长"设置对播放毫无作用 | `play_code` 空格分支 `if(s_split_time*3<80) delay(80); else delay(sp_time*3);`——条件用 s_split_time、延时却用 sp_time（=s_play_u_time），变量错位使 s_split_time 在播放路径失效 | 条件与延时应同源；此类"可配置不生效"靠最小可复现播放用例自测（见 ble-weapp-morse-trainer.md §5） |
| 135 | 【协议】向特征写入含 ≥3 个冒号的异常帧后设备死机/复位 | `ble_op_msg` 冒号分割器 `p++` 无上限、`info[p] += msg[i]` 对 3 元素数组越界写栈 | 解析器对 p 加上界（p >= 3 丢弃或并段）；外设协议必须假定对端可被伪造（异常帧即攻击面） |
| 136 | 【CW】自动键无法实现 iambic（交替补码）节奏，双桨同按只出机械交替 | 自捶用阻塞 `delay(s_u_time)`：按住期间 loop 停转，读不到另一桩状态变化，无从记忆 | 按键采集事件化（轮询+沿检测或中断置标志），时序用 esp_timer/gptimer 周期回调驱动蜂鸣 |
| 137 | 【BLE】想缩短连接间隔降低延迟，写了两个 setMinPreferred 却只生效一个 | `setMinPreferred(0x06)` 后紧跟 `setMinPreferred(0x12)`，后者覆盖前者；两行均出自官方示例的复制粘贴（单位 1.25ms） | 只保留一个目标值；连接参数协商最终以从机（手机 OS）策略为准，设置仅是建议 |
| 138 | 【内存】长时间键入练习后 BLE 发送变慢/偶丢，堆碎片化 | 39 元素 String 码表常驻堆 + `info[p] += msg[i]` 类逐字符 String 拼接高频分配释放；经典 128KB 板不致命，小 RAM/OTA 场景放大 | 码表改 `const char*` 数组；协议解析用定长 char 缓冲；BLE 热路径避免 String（本 skill 纪律 §内存） |

## POV 风扇屏/WS2812 阵列类（139–153）

| 139 | 【显示】POV 屏上传 JPEG 后画面全黑，视频模式却正常 | 亮度缩放 `outData[p]*（j+3)/300` 在 C 里是整数除法，j≤79 时恒为 0；PC 原型 Python 同公式是 float 除法——跨语言移植语义漂移 | 缩放系数先算成 float 再取整，或把除数改成位移/查表；移植数值公式时逐条核对除法语义（见 pov-fan-display.md §5） |
| 140 | 【启动】全新 flash 首次开机直接 Guru/复位，再烧一次同样崩 | littlefs `format_if_mount_failed=true` 格出空文件系统，`fopen("/littlefs/imgarrays")` 返回 NULL 未检查，`fread(NULL)` 崩在 app_main | 所有 fopen 必查返回值；首次启动检测关键文件缺失时进安全模式（黑屏+默认图案）而非裸崩 |
| 141 | 【视频】帧数统计总比实际多一，播放尾部多一帧黑屏/花屏 | `while(!feof(f))` 先判后读：EOF 要在读失败后才置位，末尾空读也 `video_page++`；`video_task` 的 `for(i<video_page-2)` 魔法 -2 就是补偿产物 | 循环条件用 `fread(...) == 48000` 的返回值；删除一切「魔法偏移」补偿，计数与真实读数对齐 |
| 142 | 【MQTT】>1KB 的 MQTT 消息收到的文件永远只有最后一小段/损坏 | esp-mqtt 默认 buffer 1024，大消息分多个 MQTT_EVENT_DATA 事件（current_data_offset/total_data_len）；代码忽略分块字段且每事件 `fopen("w")` 覆盖写，最后分块覆盖前面全部 | 按 `current_data_offset==0` 开文件、追加写、`offset+len==total` 才关；或 `mqtt_cfg.buffer.size` 调大到消息上限（见 pov-fan-display.md §7） |
| 143 | 【MQTT】设备回发大 JPEG 给 APP，APP 收到截断或直接收不到 | `esp_mqtt_client_publish` 单次发 20000B 超出默认 out_buffer，返回 -1 静默丢弃；代码不查返回值 | publish 检查返回值；大文件分片（topic 带序号）或改 HTTP 下发；esp-mqtt 不保证应用层分片 |
| 144 | 【Web】任意人访问 `/readfile?name=../../x` 能读设备任意文件、/delfile 删任意文件 | `name` 查询参数 sprintf 直拼路径零过滤 + 所有 handler CORS `*` 无认证 | 文件名白名单正则（如 `^[0-9]{4}\.jpeg$`）；跨网服务加 token；绝不对外暴露任意路径读写 |
| 145 | 【安全】公网任何人都能遥控你的设备（电机启停/文件增删） | broker 地址+账号密码硬编码在固件源码，同一账密还预填在 APP HTML input value 里；topic 无设备级隔离 | 一机一密+设备随机 ID 进 topic（参考 micropython-env-controller.md §7）；账密绝不进 HTML/源码明文 |
| 146 | 【ISR】高速定时器 ISR（100kHz）CPU 占用异常高；照示例把"秒"传给初始化函数却得到 µs 级中断 | ISR 内 `num % speed` 非幂二模除每 tick 一次；`timer_interval_sec` 形参名与实义（原始 alarm tick）不符，示例注释系统性撒谎 | 模除改递减计数器（`if(--cnt==0){cnt=speed;…}`）；读 API 先看参数换算代码而非参数名 |
| 147 | 【GPIO】输出脚电平抖动/驱动无力，万用表量到中间电平 | `gpio_config_t` 同时 `pull_down_en=1` 且 `pull_up_en=1`，上下拉打架（源工程原样复制） | 输出脚两个都关；输入脚按实际需要开且只开一个 |
| 148 | 【LED】多条 WS2812 灯带用不同 RMT 分频后时序全乱/带间闪烁 | vendored led_strip 组件把 t0h/t1l tick 存全局变量，4 条带共享；同 clk_div 侥幸无害，一旦某条改分频即互相覆盖 | 每条带独立配置实例；IDF 5.x 用官方 led_strip 组件 per-device 配置；魔改第三方组件前先审全局态 |
| 149 | 【显示】POV 显示的红蓝与原图对调（视频/图片均如此，未上板复测，以实物为准） | OpenCV `frame.tobytes()` 是 BGR 序，固件按 (R,G,B) 参数序喂 `set_pixel`，组件再按 GRB 排线——两次换序疑似差一次 | 离线导出前 `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`；固件端统一约定并写进数据格式文档 |
| 150 | 【文件】图片存到第 10 页后再也调不出来 | 上传端 `sprintf("000%d.jpeg", page)`：第 10 页存成 `00010.jpeg`；解码端 switch case 10 硬编码打开 `0010.jpeg`——同一编号两套文件名 | 文件名统一 `sprintf("%04d.jpeg", n)` 生成与解析；禁止 switch 硬编码路径与生成式并存 |
| 151 | 【解码】上传 336×256 或 >20KB 的 JPEG 后花屏/堆损坏 | `image_data[20000]` 固定读 20000B 截断大图；`outData=malloc(160*160*3)`、outW/outH 写死 160，非 160×160 图的 rect 增量写出界 | 上传前限制尺寸与体积（PC 端缩放）；或按 tjpgd_prepare 返回的实际宽高分配 outData |
| 152 | 【音频】播放 8kHz/22.05kHz 的 wav 变声快放；某些 wav 头几毫秒杂音 | I2S 速率写死 44100、`data+44` 假定 44 字节标准头，都不解析 wav fmt chunk | 解析 wav 头取真实 sample_rate/data 偏移；或统一离线转码 44100/16bit/mono 再上传 |
| 153 | 【构建】app 分区莫名紧张，1600K 放不下固件 | `EMBED_FILES "123.wav"` 把 455KB 音频链进 app 镜像，而运行时只用 littlefs 里的 music.wav（嵌入版只活在注释代码） | 用户可换资源放文件系统；EMBED 只留 bootloader 必需资产；定期 `idf.py size` 审计各段 |

使用约定：新坑追加编号＋症状原文，标注「未实测/已实测」；实测后把「以官方文档为准」替换为实测值。
