# 量产工程纪律：内存/链路/OTA/低功耗/检查清单

> 何时读：项目要从 Demo 走向量产（长时间运行、批量交付、OTA 升级、电池供电），或出现"跑几小时/几天才崩"的隐蔽问题，或需要一份上线前检查清单时读本文。
> 状态：文档沉淀（源自用户提供的《ESP32 软件开发避坑手册（量产级）》转写提炼；原则与 API 对齐官方文档，未上板实测。Demo 级写法与量产级差距主要在本文，不重复基础内容，重叠处只给指针）。

## 1. 芯片选型：不要拿 Demo 经验硬套

| 型号 | 定位 | 要点 |
|---|---|---|
| ESP32 / S3 | 双核，SRAM 大（classic≈520KB / S3≈512KB）；S3 带 PSRAM/USB OTG/Camera/LCD | 带屏、语音、轻量 AI |
| ESP32-C3 | 单核 RISC-V，≈400KB，低成本低功耗 | 简单 IoT 节点 |
| ESP32-P4 | 强算力，MIPI/H.264/JPEG，**无 WiFi/BT**，需外挂无线模组 | 视觉类（超出本 skill 三芯片范围，仅选型参考） |
| ESP32-C6 | WiFi 6/Thread/Zigbee/Matter | 智能家居多协议 |

铁律：换芯片型号后，老项目的 sdkconfig、分区表、内存分配策略**绝不直接照搬**（SRAM/IRAM/PSRAM/外设/中断特性都不同）；换型先过 datasheet 与 TRM。

## 2. 内存管理（量产崩溃一大半在这里）

**四类内存**：

| 类 | 用途 | 纪律 |
|---|---|---|
| IRAM | 中断与实时代码 | 容量有限，只给 ISR 与 flash 写期间代码，全加 IRAM_ATTR 会链接失败（坑 #83） |
| DRAM | 运行时数据与堆 | 最紧张，重点监控 |
| PSRAM | 大缓冲/图像/日志 | 慢，不能替代内部 SRAM |
| Flash | 代码/常量/分区 | 写入次数有限 |

**泄漏防治**（典型表现：运行数小时/数天后重启、malloc 返回 NULL、MQTT/OTA/WiFi 重连失败、任务创建失败）：能用 static 就不 malloc；大缓冲区初始化时一次性申请；每个 malloc 旁边立即写 free（含异常分支）；WiFi 重连缓冲、JSON 反复序列化、HTTP/MQTT 响应体、第三方库内部是高发点；定时打印 `heap_caps_get_info()` 关注 `total_free_bytes` 与 `largest_free_block`。

**碎片诊断**（坑 #82）：总空闲够 ≠ 能分配。总空闲 120KB 而最大连续块 8KB 时申请 32KB 必失败。高发：频繁 JSON 打包、日志字符串动态拼接、网络包反复分包组包、OTA 临时缓冲反复申请释放、任务/队列反复创建销毁。对策：固定大小缓冲静态分配、频繁小对象用内存池、减少运行时创建任务与队列。

**DMA**：SPI/I2S/SDMMC/摄像头缓冲必须 `heap_caps_malloc(size, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL)`（普通 malloc 的地址 DMA 不可访问），且判 NULL。

## 3. FreeRTOS 任务与栈

- **溢出检测必开**：`configCHECK_FOR_STACK_OVERFLOW = 2`；定期 `uxTaskGetStackHighWaterMark(handle)`，**水位低于 200 字必须加栈**（坑 #84）。栈不够是静默崩溃：踩相邻任务栈/全局/队列，表现为随机重启、无关任务挂掉、业务数据错乱。
- **栈经验值**：简单 IO ≥512 字；含 JSON/TLS/HTTP/MQTT ≥2048 字；printf/字符串格式化/加密/文件系统要更宽（本 skill 硬约束即按此）。
- **禁止递归**（坑 #85 关联）：任务栈仅几 KB，JSON 解析/目录遍历/递归日志改迭代或队列化。
- **优先级参考**：WiFi/系统任务最高（勿动）> 链路管理与状态机 > OTA/MQTT > 传感器/按键/LED。业务任务抢占 WiFi/MQTT 会造成假掉线。
- **双核**（classic/S3）：协议栈在 Core 0，应用放 Core 1；中断/DMA/驱动勿绑错核；跨核共享必用互斥；ISR 内禁 printf/malloc/互斥量（与 [isr-and-concurrency-rules.md](isr-and-concurrency-rules.md) 一致）。

## 4. WiFi 与网络链路

- **事件驱动，禁止轮询死等** `WiFi.status()`（阻塞+触发 WDT）：监听 `WIFI_EVENT_STA_DISCONNECTED` / `IP_EVENT_STA_GOT_IP`，断开用定时器指数退避重连，`esp_wifi_connect()` 加 8~10s 超时保护。
- **退避表**（坑 #86 关联）：失败后 1s→2s→4s→8s→16s→32s，封顶 60s；连续超限进低功率等待；密码错/AP 不存在按原因码区分，**不无限重试**。
- **双层保活识破假连接**（坑 #86）：connected ≠ 链路可用（AP 断流/路由器死机/DNS 失败/服务器不可达）。第一层看 WiFi 事件+RSSI+重传率；第二层看 MQTT keepalive（建议 30s，平台侧超时与设备匹配）或 TCP 心跳。
- **弱网限流**（坑 #87）：上一个心跳没应答不发下一个；传感器高频数据 QoS 0、控制指令 QoS 1；RSSI < −85dBm 降上报频率；OTA 期间限业务报文。

## 5. NVS 与配置存储

- **写限流**（坑 #88）：NVS 频写拖慢系统+磨损 flash+可能 `ESP_ERR_NVS_NO_FREE_PAGES`。WiFi 配置/设备参数采用**变更后延迟写入**；写入前校验；重要参数加 CRC16。
- **初始化只一次**：重复 `nvs_flash_init()` 出错；返回 `ESP_ERR_NVS_NO_FREE_PAGES`/`ESP_ERR_NVS_NEW_VERSION_FOUND` 时 `nvs_flash_erase()` 后重 init（模板 main_idf.c 已内置该范式）。
- **PHY 校准存 NVS**（坑 #89）：否则每次启动做完整 RF 校准——启动变慢、深睡唤醒后 WiFi 不稳。menuconfig 开启 PHY 校准数据存储到 NVS。

## 6. 看门狗与异常恢复

- MWDT（系统级，出事只见系统复位）与 TWDT（任务级，谁卡死一目了然），**优先 TWDT**：关键任务注册、主循环 `esp_task_wdt_reset()`、阻塞操作设超时；**不要在 ISR 里喂狗**。
- **软复位分级**：链路异常先"关 MQTT→断 WiFi→重连"，多次失败再整机重启——比直接 esp_restart() 用户体验好。

## 7. OTA 量产铁律（最容易变砖的地方）

- **A/B 分区**：分区表至少 nvs、otadata（通常 8KB，记录启动分区）、ota_0、ota_1（factory 可选）。4MB flash 挤双 OTA 槽很紧张（对照坑 #63）。
- **四步铁律**：①新固件下载到空闲分区（不动运行分区）→②MD5/SHA 校验+固件头校验→③切启动分区重启→④新固件自检通过后 `esp_ota_mark_app_valid_cancel_rollback()`。缺第④步 bootloader 判异常自动回滚；必须 `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`；量产考虑安全版本号与防回滚。
- **升级加锁**（坑 #93）：OTA 中禁配网、禁频繁重连、禁系统复位、降业务报文、心跳保持不堆积；反向同样：配网/重连期间不启动 OTA。
- **弱网断点续传**（坑 #91）：已下载偏移量存 NVS，重连后从断点继续，成功率显著提升。

## 8. Deep Sleep 与低功耗

- **唤醒后 RAM 大部分丢失**：仅 RTC RAM 与部分外设状态保留；任务栈丢、WiFi 断、TCP/MQTT 会话必须重建；全局变量不放 RTC RAM 就不能依赖。唤醒连不上 WiFi 常见原因=RF 校准数据丢失（回到 §5 PHY 校准存 NVS）。
- **定时唤醒用外部 32.768kHz 晶振**（坑 #90）：内部 RC 误差可达 ±10%，长周期定时漂移大；电池节点几乎必配。
- **三档睡眠分层**：Modem-sleep（保 WiFi 连接、CPU 跑）→ Light-sleep（CPU 停、GPIO/定时器可唤醒）→ Deep-sleep（大部分断电只留 RTC）。电池节点标准流程：定时唤醒→采集→联网上报→立即休眠，不长等 WiFi。
- **优化要有数据**：电流探头抓波形。立竿见影：WiFi 发射功率不拉满（室内 10dBm 足够）、文件写入批量 fsync、CPU 按需降频。

## 9. 串口日志与调试

- 量产不开 Debug 日志：大量 ESP_LOGD/printf 占 CPU、增 IRAM/栈压力、拖慢串口、掩盖时序问题。调试期 Debug/Info，量产 Warning/Error，关键路径日志用 `#if CONFIG_LOG_DEFAULT_LEVEL >= ESP_LOG_DEBUG` 包起来。
- printf/sprintf/snprintf 吃栈：启用 Newlib Nano formatting 降栈开销（坑 #92）。
- **开机现场**：每次重启先打印复位原因、异常核心、调用栈、堆内存、任务栈水位、最近错误码——偶现死机多从复位原因快速定位（报文解码见 [symptom-quickref.md](symptom-quickref.md)）。

## 10. 量产前检查清单（交付前逐项打勾）

| ✓ | 检查项 |
|---|---|
| ☐ | 所有 malloc 有对应 free，异常分支也覆盖 |
| ☐ | DMA 缓冲用 MALLOC_CAP_DMA 且判 NULL |
| ☐ | 任务栈开溢出检测（=2）并实测水位（>200 字余量） |
| ☐ | WiFi 事件驱动，无阻塞轮询死等 |
| ☐ | 重连有退避、有上限、有原因码区分 |
| ☐ | MQTT/TCP 有应用层心跳（keepalive ≈30s 且与平台匹配） |
| ☐ | NVS 写入限流、校验、重要参数 CRC |
| ☐ | OTA 有 A/B 分区、校验、回滚、升级互斥锁 |
| ☐ | Deep Sleep 唤醒后能稳定重连 WiFi（PHY 校准在 NVS） |
| ☐ | 日志分级，量产关 Debug；条件编译包裹 |
| ☐ | 复位原因、堆、栈水位有运行期监控 |
| ☐ | 换芯片型号后重新核对 SRAM/IRAM/PSRAM/外设/分区表 |

## 11. 坑位索引

本文相关坑位见 [known-pitfalls.md](known-pitfalls.md)「量产手册类」#82–#93：内存碎片最大块不足、IRAM 塞爆链接失败、栈水位无监测、递归爆栈、假连接、弱网猛发、NVS 频写磨损、PHY 校准缺失、RC 晶振漂移、OTA 无断点续传、量产 Debug 日志、OTA 无互斥锁。
