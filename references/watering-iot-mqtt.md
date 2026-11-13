# IoT 自动浇水控制器（esp32-watering 转写：MicroPython 设备端 + 自建 MQTT 服务端）

> 何时读：需要打通「土壤湿度传感器 → MQTT 云端 → 水泵执行器」闭环、做土壤湿度标定、驱动 L9110S／继电器、给无 NTP 设备做校时，或需要一份设备端 ↔ 云端 MQTT 契约的完整样例时读。
> 状态：知识沉淀（源工程已运行、固件逐行核对；MicroPython v1.28.0 口径，服务端 .NET 9 侧仅作契约对照；ESP32 固件未二次上板复测）。

## 1. 系统定位与双设备形态

一个「家用级、单服务端、多设备」的物联网浇水系统：服务端内嵌 MQTT Broker + Blazor 管理台，设备侧全部 MicroPython，两种硬件各司其职。

| 维度 | 设备 A：ESP32 自动浇水 | 设备 B：ESP-01 定时浇水 |
|---|---|---|
| 芯片 | ESP32-WROOM-32（MicroPython v1.28.0，刷写地址 0x1000） | ESP-01 1MB（ESP8266_GENERIC-FLASH_1M 固件，刷写地址 0x0，波特率 115200） |
| 传感器 | 土壤湿度 AO → GPIO34 | 无 |
| 执行器 | L9110S H 桥 → 小水泵 | 双继电器模块 → 两路水泵 |
| 决策 | 本地阈值自动浇水 + MQTT 远程 | 纯定时：HTTPS 拉时间组 + 远程 |
| 云端交互 | 仅 MQTT（4 主题） | MQTT + HTTP GET 定时配置 |
| 固件 | tools/Esp32Mpy/main.py（276 行） | tools/Esp8266Relay/main.py（369 行）+ 手传 umqtt/simple.py |

文件布局：`tools/Esp32Mpy/main.py`、`tools/Esp8266Relay/main.py`、`docs/soil-moisture-calibration.md`、`docs/hardware-guide.md`、服务端 `src/Esp32Watering.Server/`（MqttBrokerService / MqttClientService / DeviceDataService / DeviceHeartbeatService）。

## 2. 硬件与接线事实

### ESP32 + L9110S + 电阻式/电容式土壤传感器

| 引脚 | 用途 | 约束 |
|---|---|---|
| GPIO34 | 土壤湿度 AO | 输入专用脚，ADC1_CH6，只能输入 |
| GPIO26 | L9110S B-1A | PWM 调速（MicroPython duty 0–1023） |
| GPIO27 | L9110S B-1B | 方向电平 |
| GPIO2 | 板载 LED | 闪烁=正常，长亮=异常 |
| 3.3V / 5V / GND | 传感器 / L9110S / 共地 | 水泵 >200mA 时 L9110S 用独立 5V，别从 ESP32 取电 |

### ESP-01 + 双继电器模块

| 引脚 | 用途 | 约束 |
|---|---|---|
| GPIO0 | 继电器 IN1（低电平触发） | ESP8266 strapping 脚：低电平=下载模式 |
| GPIO2 | 继电器 IN2（低电平触发） | 同为 strapping 脚，复位需高 |
| 3.3V/GND | 模块供电 | 模块自带 5V 升压，3.3V 输入 |

继电器是低电平触发，固件初始化 `Pin(0, OUT, value=1)` / `Pin(2, OUT, value=1)`——代码加载前的浮空窗口仍有上电瞬态风险（见坑 181）。

## 3. 土壤湿度传感器实测标定（本工程最有复用价值的数据）

同一块 ESP32、GPIO34、`adc.read_u16() >> 4` 读 12 位原始值（0–4095）的实测结果：

| 测量条件 | 电阻式 ADC | 电容式 ADC |
|---|---|---|
| 空气中 | 4095（基准） | 3312（基准） |
| 干燥土中 | 4095 | 3161 |
| 较干燥土中 | 3253 | 2539 |
| 湿润土中 | 1623 | 1936 |
| 水中 | 2178（**异常回升**） | 1297（单调递减） |

结论：**两种传感器都是「越湿 ADC 越低」**（电阻式约 1500–4095 区间可用，但水中回升说明其只适合定性判断干湿趋势）；电容式单调、线性度好，适合定量。

推荐阈值（原始值，非百分比）：电阻式 `MOISTURE_THRESHOLD = 3800`（>3800 判干触发浇水）；电容式 `3000`。固件默认 3000 是按电容式写的。

ADC 注意：ESP32 ADC 非线性、板间离散，阈值必须按自己的探头实测；`read_u16()>>4` 得到 12 位值，`read_u16()` 本身是 16 位；GPIO34 无内部上拉/下拉，悬空读数漂移。电阻式探头长期带电插在土里会电解腐蚀（几个月报废），选镀金/镀镍腐蚀抑制型探头，或只在测量时给探头供电。

## 4. L9110S 驱动逻辑

| 动作 | B-1A (GPIO26) | B-1B (GPIO27) |
|---|---|---|
| 正转（PWM 调速） | `PWM.duty(800)` ≈78% | LOW |
| 反转 | LOW | HIGH |
| 停止 | `duty(0)` | LOW |
| 刹车（短接电机） | HIGH | HIGH |

MicroPython duty 是 0–1023（10 位），Arduino 是 0–255（8 位）：`duty(800)` ≈ `analogWrite(26, 200)`。两引脚都置 LOW 才是「停止 + 不制动」；本项目只用正转。PWM 频率 1000Hz 会有可闻啸叫，改 20kHz 以上更安静（L9110S 支持，以数据手册为准）。

## 5. ESP32 固件结构与控制纪律

主循环 1s tick，各职责靠时间差触发，不用 RTOS 任务（MicroPython 单线程）：

| 周期 | 动作 |
|---|---|
| 10s | `ensure_mqtt()`（内含 `ensure_wifi()`）探活/重连 |
| 30s | 心跳 `publish(status, "online")` |
| 60s | `adc.read_u16()>>4` → 有效窗校验 → 上报 → 自动浇水判定 |
| 每 tick | 检查浇水是否到点停止；LED 状态机（1s 闪／常亮） |

连接函数的设计是「单函数自愈」：`ensure_wifi()` 先 `active(False)` 再 `active(True)` 重置（规避 ESP32 MicroPython 的 `Internal State Error`——这是源工程实际踩过的坑），`ensure_mqtt()` 用 `client.ping()` 探活，失败则 `disconnect()` 清理后重建并重新 `subscribe`。

浇水状态机的最小安全集（值得照抄）：

- **重入保护**：`watering_active` 为真时直接返回，重复指令不会叠加。
- **冷却期**：`WATERING_COOLDOWN = 30s`，`now - last_watering_end_time` 不够就不浇，防频繁启停烧泵。
- **传感器有效窗**：`< 50` 判断线、`> 4000` 判异常，异常读数只打日志不触发浇水——探头脱土/短路时不会「一直浇」。
- **停止时发 ACK**：`stop_watering()` 里 `publish(ack, "1")`。

时间语义：`utime.time()` 只用来算差值（`stop_time = time() + duration`），不需要绝对时间。**MicroPython 的 ESP8266/ESP32 端口 epoch 是 2000-01-01 而不是 Unix epoch**（以官方文档为准），拿 `time()` 和服务器 Unix 时间戳直接比较会差约 30 年。

## 6. ESP-01 无 NTP 定时方案（四步校时）

ESP-01 没有 RTC 备份电池，断电即丢时间。固件用服务端时间做唯一时源：

```
GET /api/config/scheduled-watering
{ "enabled": true, "serverDate": "2026-06-14", "serverTime": "15:30",
  "timeGroups": [ {"time":"08:00","durationSeconds":10}, {"time":"20:00","durationSeconds":15} ] }
```

`serverDate`/`serverTime` 是 **UTC**（服务端 `DateTime.UtcNow`）。写入 RTC 四步：

```python
secs = utime.mktime((y, m, d, h, mi, 0, 0, 0)) + TZ_OFFSET_HOURS * 3600   # 8
lt   = utime.localtime(secs)                    # 自动处理跨日
machine.RTC().datetime((lt[0], lt[1], lt[2], 0, lt[3], lt[4], lt[5], 0)) # weekday 位填 0
```

要点：`mktime`/`localtime` 同端口同 epoch 自洽，跨日由 `localtime` 处理；`rtc_initialized=False` 时 `check_schedule()` 直接跳过——**时间不可信就不执行定时浇水**，这是防「上电即误浇」的关键开关。

定时去重用一次性 key，跨日自动失效，不需要维护「今日已执行」集合：

```python
key = today + "_" + group_time      # "2026-06-14_08:00"
if key == last_executed_key: continue
```

网络侧纪律（1MB ESP8266 的生存线）：模块顶部 `usocket.setdefaulttimeout(8)` 统一 socket 超时；`fetch_schedule()` 用 `urequests` 且 `resp.close()` 放 `finally`；未校准时 30s 重试、校准后 300s 刷新一次——**TLS 握手在 1MB 设备上偶发失败且吃内存，降频是防死机手段**（源工程 CHANGELOG 记录过 socket 泄漏修复与「降频防死机」）。

## 7. MQTT 契约与两处语义漂移

统一前缀 `esp32/{id}`（ESP-01 也复用，服务端零改动）：

| 主题 | 方向 | 载荷 |
|---|---|---|
| `esp32/{id}/soil_moisture` | 设备→云 | 原始值字符串 "0"–"4095"（越干越大） |
| `esp32/{id}/status` | 设备→云 | "online"（30s 心跳） |
| `esp32/{id}/watering/cmd` | 云→设备 | "1" |
| `esp32/{id}/watering/ack` | 设备→云 | "1" |

两处契约缺陷值得改（本工程未改）：

1. **ACK 语义相反**：ESP32 在**停止时**发 ACK（表示完成），ESP-01 在**开始时**发 ACK（表示已执行）。服务端拿到 "1" 无法区分「已开始/已完成」。
2. **指令无参数**：`"1"` 不带时长，远程浇水只能吃固件常量（10s / 30s）；想下发 5s 必须改固件重刷。建议主题载荷改 JSON：`{"cmd":"water","duration":5}`。

另外两个缺失：没有 LWT（`will_set`），设备掉电后服务端要等 120s 心跳超时才判离线；没有「offline」上报（文档明确写了「设备无需上报 offline」，是取舍不是遗漏）。

## 8. 服务端角色（只作契约对照，不在本技能范围）

- **MqttBrokerService**：内嵌 MQTTnet Broker，1883，账号密码认证（默认 `esp32` / `esp32@2026`；配置留空则无认证）。
- **MqttClientService**：订阅设备主题（`PublishAsync` 返回 bool，发送失败前端能感知）。
- **DeviceDataService**：湿度/浇水记录落 SQLite，同时广播 SignalR。
- **DeviceHeartbeatService**：30s 扫描、120s 无数据标离线，离线时广播 `DeviceStatusChanged`。
- **ScheduledWateringConfig API**：时间组 + `serverDate/serverTime` 校时。
- SignalR：`/hubs/watering`，`MoistureDataReceived(deviceId, moistureValue, isOnline)`、`DeviceStatusChanged(deviceId, isOnline)`、`WateringCommandSent(deviceId, command)`（最后一条只推设备组 `device_{id}`）。
- 部署坑：`dotnet publish` 在 Windows 上不要加 `-r linux-x64`，会破坏 Blazor WASM 产物。

## 9. 安全与运维清单（照抄前必改）

| 项 | 现状 | 应有做法 |
|---|---|---|
| WiFi/MQTT 凭证 | 明文写死 main.py（ESP-01 固件还含真实家宽 SSID/密码与生产域名） | 占位符 + 首启配网（AP 表单/BLE）或 secrets 分区 |
| MQTT_BROKER 默认值 | `127.0.0.1`——设备上指自己，永远连不上 | 出厂模板置空，首启必填 |
| 看门狗 | 无 | `machine.WDT(timeout=…)` + 主循环喂狗 |
| OTA | 无 | 至少预留版本号与远程升级通道 |
| 重连节奏 | 10s 固定周期，无退避 | 指数退避 + 随机抖动 |
| 生产证书 | HTTPS 由 urequests 默认校验（ESP8266 需 axtls 根证书集，以固件为准） | 明确根证书与失败策略 |

## 10. 可复用模式（6 条）

1. 单函数自愈连接器：`ensure_wifi` / `ensure_mqtt` 各自处理「断开→清理→重建→重订阅」，主循环只调一次。
2. 时间差驱动的主循环：所有周期任务用 `now - last_x >= period`，无定时器中断、无任务。
3. 有效窗 + 冷却 + 重入，三件套把「执行器意外长开」的概率压到最低。
4. 无 NTP 设备用「业务 API 顺带返回服务器时间」校时，比引入 SNTP 更省依赖（校时失败就不执行定时）。
5. 一次性执行 key（`date_time`）替代「今日已执行」集合，跨日自动失效。
6. 服务端内嵌 Broker：设备零依赖公网 Broker，MQTT + SignalR + 前端一体，适合家用/小规模部署。

## 11. 坑位索引

- 配置类：坑 174（默认 broker 127.0.0.1）、175（固件明文凭证）、183（1MB 固件无 umqtt）
- 时序类：坑 176（网络阻塞拉长浇水）、177（RTC 重校时跳变）、182（epoch 混用）、186（无看门狗）
- 契约类：坑 178（无 LWT）、179（ACK 语义相反）、180（指令无参数）
- 硬件类：坑 181（GPIO0/2 strapping + 低电平触发）、185（探头电解腐蚀）、187（原始值当百分比）
- 文档类：坑 184（湿度方向描述与实测表相反）
