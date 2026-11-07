# MicroPython 商用环境控制器工程范式（env-controller 转写）

> 何时读：要在 ESP32 上用 **MicroPython** 做多服务商用固件（asyncio 服务化、Modbus 主/从站、RS485、MQTT/Home Assistant、涂鸦 TuyaLink 云对接、规则引擎、Web 配置、防变砖 OTA）时读；也适合评估"MicroPython 能不能上量产"。
> 状态：实战档。源自已部署商用工程 env-controller v1.5.1-beta（ESP32-S3 N16R8，自编译 MicroPython v1.28 固件）；本文为源码转写、未在本机二次复测。源码 `D:\ESP32project\env-controller-master`。

## 1. 系统定位

商用环境控制器：8 路 DI + 10 路 ADC + 多路 Modbus 传感器轮询 + 三类执行器输出 + 规则联动/告警 + 双网（WiFi + W5500 以太网）+ 四种上行（Web/microdot、Modbus-TCP、MQTT/HA、涂鸦云）。**全 asyncio 单线程事件循环，无 _thread，10 个服务**。配置全驱动（无内置传感器型号清单）。

启动链（flash 上唯一明文）：

```python
# main.py 全部内容（9 行）
import app_main
_sys.modules['main'] = app_main      # 别名技巧：import main 读到 app_main，不重复执行
asyncio.run(app_main.main())
```

服务化骨架（app_main.py:103-105,502-527）：

| 机制 | 写法 |
|---|---|
| 启动顺序 | `SERVICES = [...]` 列表，逐个 `__import__(mod)` + `asyncio.create_task(mod.start(net))` |
| 崩溃捕获 | 每个 task `add_done_callback` 记状态，供 /api/status 健康上报 |
| 服务间数据 | 模块级中间件 `lib.common.latest_data`（get/set，防 import main 重执行，也解循环导入） |
| 网络看门狗 | `_net_watchdog` 60s 双网独立 socket 探网关；连续 2 次失败才动作；W5500 假死 **不** `nic.active(False)`（破坏 SPI 状态），>5min `machine.reset()` 整机重启 |
| 时间 | RTC 年<2020 每 30s 重试 NTP，成功后 6h 校准一次；写回外部 PCF85063A（docs 写 PCF8563 已过时） |

## 2. MicroPython on ESP32 工程事实

| 主题 | 事实 |
|---|---|
| 固件 | 自编译 v1.28 `ENVCTRL_S3-SPIRAM_OCT`（16MB flash + 8MB PSRAM）；应用=LittleFS 14MB，mklittlefs 打包拼入固件 0x200000 偏移，esptool 烧 0 地址 |
| C 模块 | `USER_C_MODULES` 编入固件（micropython.cmake），非 .mpy 非冻结；Python 侧 `hasattr` 检测、无则回退纯 Python（uart.py:10-17） |
| import 优先级 | `.py` 优先于 `.mpy`——OTA 覆盖 .mpy 时必须把旧 .py 同步改 `.upg.bak`，否则新代码不生效（坑 #113） |
| GC 策略 | `gc.threshold(4*1024*1024)`：堆剩<4MB 主动小步 GC，避免堆耗尽触发一次释放 7MB、阻塞数百 ms 的大 GC（app_main.py:365-373） |
| 阻塞纪律 | SD 同步写阻塞 100ms+ → 心跳/请求路径不落 SD；`gc.mem_free/alloc` 每次约 15ms → 30s 才采一次 |
| 系统补丁 | 覆写 `builtins.print` 加时间戳；启动期 monkey-patch v1.28 `IOQueue.wait_io_event`——对失效 socket 抛 OSError(EIO) 会崩整个事件循环，补丁重建 poll 只剔失效 fd（app_main.py:32-100，坑 #103） |
| 大文件 | web_service.py 117KB/2695 行 = 业务 + vendored microdot(1605 行)；启动预热 config/SD 缓存 + `gc.collect`，防首次请求大分配打断 W5500 SPI |

## 3. 传感器层（Modbus 主站，配置驱动）

指令 schema：`commands[{function_code(1-4), start_addr, count, polling, channels[]}]`，通道 `{offset,len,scale,unit,byte_order,bit,datatype}`（旧 registers 格式自动迁移）。

- 解析（sensor_service.py:113-122）：FC3/4 按字节段切；float=IEEE754 两寄存器 `struct.unpack`；bit 位拆分；**符号扩展仅 s16/s32/int**——u16 曾把 40000 显示成 -25536（坑 #110）。
- 轮询韧性：失败继承旧值不留空洞；write_busy 跳读；写后 2s 冷却；RS485 长帧被 CRC 丢弃后**立即补读一次**（成功率>90%）；`poll_interval` 强制 ≥1 防 ZeroDivisionError。
- UART 自愈：读超时 3s / 外层 `wait_for` 8s；连续 3 次超时 + 过 60s 启动保护期 + 限频 60s 一次才重建 UART，重建后 `rebind_uart` 同步输出设备。
- ADC：仅 ADC1 GPIO1-10（**WiFi 下 ADC2 不可用**）；ATTN_11DB 0-3.3V；1s 周期 16 次均值 × 线性 scale（无两点校准）。
- 历史：每轮 poll append `/sd/data_YYYYMMDD.csv`（SD 缺回退 flash 限 2000 行/天；列=表头∪新列定序；30 天清理）。

## 4. 输出层

| 通道类型 | 要点 |
|---|---|
| Modbus 输出 | FC05/06/0F/10；国产继电器 FC01 读回是**整组 8 位位图**→按 `register_address%8` 取位；某模块 FC01 仅支持 count=1 逐通道读 |
| I2C DO 扩展 | TCA9554 系（tca9554/tca9554a/pca9554/pcf8574/pca8574），addr 0x20-0x27；TCA9554 寄存器 0x01=输出/0x03=配置；PCF8574 准双向需本地闩锁 `_latch` |
| GPIO 输出 | 普通 + 点动 jog（无论开是否成功都执行关） |

纪律：统一入口 `trigger_channel/set_channel` 同通道 **500ms 节流**（Web/联动/从站/MQTT 全平台统一）；告警通道（默认 DO1）拒绝手动/联动写，仅告警状态机 `allow_alarm=True` 放行；**上电立即状态回读**防"重启后继电器显示全关"；配置重载 `preserve=True` 保持当前输出；判断协程用 `hasattr(result,'send')`（MicroPython 无 `types.iscoroutine`）。

## 5. Modbus RTU 从站 + TCP

- RTU 独立 UART（默认 UART2 9600 8N1 tx43/rx44）+ TCP 502 共用映射核心；FC 01/02/03/04/05/06/0F/10；MAX_REG=125。
- 寄存器映射**自动生成**：保持区 0x00=DI 打包(bit0-7) / 0x01=DO 打包 / 0x02 起按配置序排传感器+输出通道；位区 0x00-0x07=DI / 0x08-0x0F=DO。
- 数据类型：每点恒 1 寄存器，小数 `_scale_int ×10^k` 整数化（272.0→2720）；写仅作用输出通道（异常码 02）；FC05 单写只翻转目标位不清其余 DO。
- TCP 防冻（坑 #109）：`asyncio.start_server` 每连接一任务，~25 连接/s 连断风暴冻结整个事件循环 → 改**单任务非阻塞 socket**：MAX_TCP_CONN=6 / TCP_IDLE_MS=15000 / TCP_BUF_MAX=2048 防恶意 length 撑爆内存。
- RS485 DE 方向：从站侧 Python 实现（DE 高→200us→write→hold→DE 低）；主站侧走 C 模块 `de_write` 硬件判定发完立即释放（Python 粗估 +10ms 过长、asyncio 短睡眠被吞 DE 卡高，坑 #106）。⚠️ 从站默认 43/44 会夺走 UART0（ESP-IDF 日志口）。

## 6. MQTT + Home Assistant

- **自写极简 MQTT 3.1.1 客户端**：umqtt.simple 的 user/password CONNECT 编码有 bug 被 broker RST（坑 #114）；分片发送 ≤128B（设备栈单次 send 限制）；TLS 1.2/8883；TLS 空读 ≠ 断线（mbedtls 非阻塞返回空）。
- 自定义模式：`{topic}` 周期 DATA 上行（仅传感器，固定键序）+ `/cmd` 下行 + `/result` 必回执 + `/alarm` QoS0；重连=主循环 0.5s 检测（曾 is_connected 恒 True 假死）+ 30s 静默重连重订阅。
- HA 模式（与自定义单活互斥）：HADriver 复用同一 MQTT 连接；Discovery retained 声明 `homeassistant/<组件>/envc_<SN>/<key>/config`；`/ha_disc.json` 持久化上一轮实体清单，**diff 后对已删实体发空 retain 清理**；unit→device_class 映射，`℃`(U+2103) 必须规范化 `°C` 否则 HA 丢弃实体；每条 discovery 间隔 15ms 防网络栈大包错位。

## 7. 涂鸦 TuyaLink 直连

- ESP32 以"直连设备"身份标准 MQTT over TLS 8883 接入涂鸦 IoT，**不依赖涂鸦模组**；一机一密：`password=HMAC-SHA256(deviceSecret, 'deviceId=..,timestamp=..,secureMode=1,accessType=1')` hex（C 模块 modtuyacrypto；Python 回退注意 `hashlib` 无 `hexdigest()`，须 `ubinascii.hexlify(digest()).decode()`）。
- timestamp 参与 HMAC → RTC 未同步(<2020)先等 NTP。
- 物模型：连接后 `thing/model/get` 拉取 properties/actions/events 缓存，**只上报平台已定义属性**（防 2006 错误）。
- DP 绑定 `tuya_map`：来源"设备.通道"=只读上报（值变化才发 + 300s 全量对账）；"out:设备id.通道序号"=可写（云端 set/action→trigger_channel）；"alarm:on|off"=告警事件；枚举=平台 range↔本地预设按序换算。
- ⚠️ 当前 `tls_insecure=True`（调试期不校验 CA，安全隐患，源码 tuya_link_service.py:826 如实记录）。

## 8. 规则引擎 + 告警状态机

- 两段存储 linkage_rules/alarm_rules（旧单数组自动迁移）；**稳定 id 'r<序号>'**（曾用 `id(rule)` 对象地址，热更新后重复告警）。
- 条件：value/bool/state(high/low/rising/falling) + and/or；**滞回**=上浮/下浮（>30 上浮 1 下浮 2 = 超 31 触发、回 28 恢复）。
- 触发：告警仅 changed 边沿触发一次；联动 level/interval/changed（interval 不拦状态变化）；**告警恢复需连续 2 轮不满足**；数据缺失跳过本轮。
- 动作：trigger/on/off/jog/write + delay_ms + else_actions；全立即时 `asyncio.gather` 并发，含延时时串行 +100ms 间隔防 Modbus 写冲突。
- 告警：4 级（≥3 驱动 DO1）、布防时间段+持续时长+自动复位；`reset`=关 DO1 但**不结束告警**（待新 alarm_on 才恢复动作）；事件 seq 单调递增缓存 20 条供 HTTP 增量补拉。

## 9. 配置三轨持久化

| 轨 | 用途 | 要点 |
|---|---|---|
| NVS 命名空间 'envctrl' | 小配置（sys/sensor/output/rules_cfg） | 单条≤4KB，**复用单句柄**防 ENOMEM |
| flash JSON | 超限大配置（/sensor.json 等） | NVS 写失败自动降级到此 |
| /engineer.json | 工程键（40 余键白名单：eth_*/uart_*/mb_slave_*/tuya_*…） | OTA 白名单排除它——升级不带走过台数据 |

纪律：DEFAULT_CONFIG 全字符串值；外设默认全关；**增量合并保存**（以现有 NVS 为底，防部分提交重置 wifi/mqtt）；导出覆盖前 `.bak`；SN='EC'+`unique_id()` hex 14 位。

## 10. Web 服务（vendored microdot）

- 0.0.0.0:80 双网可达；静态 /html/ 优先 /sd/ 回退、仅取文件名防穿越；**Request.max_content_length=4MB**（默认 16KB 曾致大配置保存静默失败，坑 #102）。
- 认证：/api/login 发 token（`os.urandom(8)` hex，RAM 会话 24h）；角色 admin/engineer；**默认 admin/admin、engineer/engineer**（docs/API.md 未更新的旧密码已过时）。
- EADDRINUSE=软复位后 lwIP 残留 LISTEN：重试 10 次仍占用提示断电（不能靠再软复位解决）。

## 11. 防变砖 OTA + 设备发现

- update.tar 结构：main.py 明文 + 其余全 .mpy（v6 字节码，绑定固件 v1.28）+ html/ 静态资源。
- 校验链（任一失败整包拒绝、统一报"校验不通过"）：tar 头 checksum(偏移 148 八进制) → 数据截断检测 → 必含 main.py → 路径白名单（13 个 .py + /lib/ + /html/ 递归，排除 engineer.json）→ 拒绝明文 .py → .mpy 头 0x4D 且版本=6。
- 原子覆盖：旧文件→`.upg.bak` 再写新；.mpy 覆盖时同名 .py 同步 .upg.bak（import 优先 .py）；写失败自动回滚；成功自动重启；进度 stage=upload→verify→cover→reboot。
- 烧录：envctrl_flash.exe=esptool `--chip esp32s3 write_flash 0` 合并 bin；16MB@115200 约 24 分钟、460800 约 6 分钟。
- 发现协议：UDP 组播 239.255.60.60:48899 每 10s 广播 {sn,version,wifi{},eth{}}，支持 query 单播应答；PC 工具 tkinter GUI，25s 无广播判离线；⚠️ 设备侧 UDP set_ip 指令**无 token 校验**（与 FEATURES 文档表述有出入，如实记录）。

## 12. W5500 以太网（全链路 C 下沉）

- 动机：软复位只重启 ESP32、W5500 不断电；Python `sleep` 估算复位在反复软复位后不可靠 → C 模块 modwizeth：RST 硬脉冲(低 300ms 高 100ms)→复用 Python SPI 对象(`machine_hw_spi_get_host`)→`esp_eth_mac_new_w5500`(SPI mode0 **4MHz** queue20)→`esp_eth_driver_install`→`esp_netif_attach`→`esp_eth_start`；deinit 可原地重挂。
- **`_spi_keep` 模块级引用钉住 SPI 对象**：被 GC 析构会 deinit 已交 esp_eth 接管的外设，表现为 web 首请求后 `spi transmit failed` 刷屏（坑 #105）。
- SPI 4MHz 实测最优、8MHz 明显恶化；与 WiFi 双栈同时工作；WiFi 省电 min 减少射频对 W5500 SPI 干扰。

## 13. 迁移结论（C_MIGRATION_REPORT）

MicroPython→ESP-IDF C 全量迁移：技术可行但性价比低；迁移动机（~80KB 堆紧张）随 8MB PSRAM 消失。基线 Python 13,244 行 + 9 服务 + 40 路由，前端 5,228 行可 100% 复用。风险在隐性契约（dict 键序/JSON 细节）与并发语义（节流/告警豁免），验收靠 Golden 对照逐路由 diff。**结论：现状不动，痛点走 C 扩展渐进下沉**——已落地三件（RS485 时序 / TuyaHMAC / W5500），Python 实现保留为回退。

## 14. 可复用模式

1. 服务化 asyncio 单循环：SERVICES 列表 + create_task + done_callback + status 健康上报。
2. 数据中枢中间件 latest_data：解循环导入 + 固定键序 schema + 序列化缓存 TTL 4s。
3. 一份 schema 三视图：serialize_latest 参数化生成 Web(meta)/MQTT(仅传感器)/HA 数据。
4. 配置三轨分层：NVS 小 / flash JSON 大 / 工程键白名单 + 增量合并 + .bak。
5. C 扩展渐进下沉：hasattr 检测自动回退，C 只做时序敏感底层。
6. 防变砖 OTA：tar 校验链 + mpy 版本绑定 + 原子覆盖 + 自动回滚。
7. UDP 组播发现：周期广播 + query 应答 + SN 身份。
8. HA Discovery 实体生命周期：ha_disc.json 基线 diff + 空 retain 清理。
9. unit→device_class/实体类型推断：枚举→select、数值→number 降级链。
10. 声明式规则 DSL：条件/滞回/边沿/interval 节流/else_actions + 稳定 id。
11. 告警状态机：多告警 key 去重 + seq 增量 + reset 静音语义（参考 ISA-18.2 分级）。
12. MicroPython 并发安全睡眠：`ticks_ms` 硬超时 + `sleep(0)` 纯 yield，规避 asyncio.sleep 小数共享单例被吞（坑 #111）。

## 15. 坑位索引

本文对应 known-pitfalls.md #102–115（#102 microdot body 上限 / #103 IOQueue 崩溃 / #104 大 GC 停顿 / #105 SPI 被 GC / #106 RS485 DE 时序 / #107 帧空闲判定 / #108 写回显误判 / #109 Modbus-TCP 冻结 / #110 u16 符号扩展 / #111 asyncio.sleep 被吞 / #112 import main 重执行 / #113 .py 优先 .mpy / #114 MQTT 认证+假死 / #115 OTA 变砖链）。
