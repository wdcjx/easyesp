# Wi-Fi NAT 中继路由器（APSTA + NAPT · ESP-IDF 5.x）

> 何时读：要把 ESP32 做成「Wi-Fi 中继器/随身路由」——STA 连上级 Wi-Fi、SoftAP 给下游设备发网、AP 侧客户端经 NAT 上网。只做普通 STA/AP 收发看 wifi-networking.md §2-§4 即可，不必读本文。
> 状态：实战项目沉淀（源自 esp32s3-wifi-relay，ESP32-S3 + ESP-IDF 5.5.5，README 附实测核对清单；本文为源码精读转写、未在本机二次复测；API 对齐 ESP-IDF 5.3+/5.5，老写法差异逐条标注，以官方文档为准）。

来源与适用性：

| 维度 | 事实 |
|---|---|
| 源工程 | esp32s3-wifi-relay（ESP32-S3 Wi-Fi NAT Router） |
| 规模 | 单文件 main.c 586 行 + sdkconfig.defaults 5 行；无自定义组件 |
| 框架 | ESP-IDF 5.5.5（`idf.py set-target esp32s3`） |
| 实测 | README §23 核对清单：STA+SoftAP/DHCP/NAT/DNS/自动重连/AP 客户端上 Internet 全 ✓ |
| 上游 | 功能对齐 martin-ger/esp32_nat_router（老牌 ESP32 NAT 路由器，带 Web 控制台） |

## 1. 数据面与两个唯一关键调用

```
AP 客户端 → SoftAP(192.168.4.1) → NAPT → STA(192.168.3.x) → 上级路由 → Internet
```

NAT 功能的全部代码只有两步（main.c `enable_napt()`）：

```c
/* ① STA 必须先成为默认网络接口（否则 AP 侧流量不知道从哪出） */
ESP_ERROR_CHECK(esp_netif_set_default_netif(s_sta_netif));
/* ② 在 AP 接口上开 NAPT —— 这一行就是"路由器"本体 */
esp_err_t ret = esp_netif_napt_enable(s_ap_netif);   // IDF 5.x esp_netif API
```

- `esp_netif_napt_enable(esp_netif_t*)` 是 IDF 5.x 的封装；老教程/上游 martin-ger 用 lwIP 裸接口 `ip_napt_enable(ip)`（以官方文档为准，两者语义相同）
- **前提 sdkconfig**：`CONFIG_LWIP_IP4_NAPT=y`（menuconfig 路径 Component config → LWIP；漏配则 NAPT API 不可用，编译期即报 undefined）
- 本工程 sdkconfig.defaults 全量 5 行，值得整段抄：

```ini
CONFIG_LWIP_IP4_NAPT=y                  # NAPT 转发本体
CONFIG_ESP_WIFI_SOFTAP_SUPPORT=y        # SoftAP 支持
CONFIG_ESP_WIFI_STA_DISCONNECTED_PM_ENABLE=y  # STA 断开时省电
CONFIG_LWIP_IPV4=y
CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=32      # TCP/IP 邮箱队列，吞吐调优点
```

- CMake 依赖仅三个：`REQUIRES esp_wifi esp_netif nvs_flash`

## 2. 网络接口与 IP 规划（esp_netif 默认值即路由器形态）

```c
s_ap_netif  = esp_netif_create_default_wifi_ap();   // 默认 192.168.4.1 + 自带 DHCP server
s_sta_netif = esp_netif_create_default_wifi_sta();  // 上级 DHCP 客户端
```

| 接口 | IP | 角色 |
|---|---|---|
| AP | 192.168.4.1（默认，勿手改） | DHCP server：AP 客户端拿 192.168.4.x，网关=192.168.4.1 |
| STA | 上级分配（如 192.168.3.78） | 上行默认路由 |
| DNS | STA 拿到 IP 后 `set dns to:<上级网关>`（README 实测日志） | AP 客户端经 ESP32 用上级 DNS |

两个 `create_default_wifi_*` 的顺序没有讲究，但**两者都必须创建**——APSTA 模式缺任一 netif，NAPT 无从挂载。

## 3. WIFI_MODE_APSTA 配置全字段（照抄可编译）

STA 侧（重点字段全开）：

```c
wifi_config_t sta_config = {
    .sta = {
        .ssid = STA_SSID, .password = STA_PASSWORD,
        .scan_method = WIFI_ALL_CHANNEL_SCAN,          // 扫全信道，别用 FAST（首连更快但漏 AP）
        .threshold.authmode = WIFI_AUTH_WPA2_PSK,      // 低于 WPA2 的 AP 拒连
        .sae_pwe_h2e = WPA3_SAE_PWE_BOTH,              // WPA3 SAE 兼容哈希到元素
        .failure_retry_cnt = 5,                        // 驱动层内部重试
    }
};
```

AP 侧：

```c
wifi_config_t ap_config = {
    .ap = {
        .ssid = AP_SSID, .ssid_len = strlen(AP_SSID),
        .channel = AP_CHANNEL,          // 仅初始值！见 §4 信道跟随
        .password = AP_PASSWORD,
        .max_connection = 8,
        .authmode = WIFI_AUTH_WPA2_PSK,
        .pmf_cfg = { .required = false },   // WPA2 不强制 PMF，兼容老设备
    }
};
if (strlen(AP_PASSWORD) == 0) ap_config.ap.authmode = WIFI_AUTH_OPEN;  // 空密码→开放网络
```

事件注册面：`WIFI_EVENT` 用 `ESP_EVENT_ANY_ID` 一网打尽，`IP_EVENT` 只挂 `IP_EVENT_STA_GOT_IP` / `IP_EVENT_STA_LOST_IP` 两个——这是 APSTA 最小事件集。

## 4. APSTA 信道跟随（射频共享的物理约束）

STA 与 SoftAP **共用同一射频**，SoftAP 信道被驱动强制跟随 STA 所连上级 AP 的信道：

- `ap_config.ap.channel = 1` 只是初始配置，运行时无意义
- README 实测日志证据：`wifi:new:<11,2>, old:<11,0>, ap:<11,2>, sta:<11,2>`——AP 与 STA 最终同在信道 11
- 推论：上级 AP 是 5 GHz 时 ESP32（仅 2.4 GHz）无法中继；上级换信道，热点全体客户端被动跟随（短暂掉线）

## 5. 启动序列：AP 先活、STA 后联（可服务性设计）

```
init_nvs → init_netif(AP+STA) → init_wifi(APSTA+start)
→ 轮询 STA IP：最多 60×500ms=30s（有限等待，不阻塞）
→ 无论 STA 是否拿到 IP 都 enable_napt()
→ 主循环每 10s 打印 STA IP 状态
```

- STA 断线重连策略：事件层计数 ≤10 次 `esp_wifi_connect()`，超 10 次清零 + 睡 2s + 继续连 = **永不放弃、永不进配网模式**——对常电路由器正确；电池设备照抄就是灾难
- NAPT 在 STA 无 IP 时也开：注释明说「STA 以后获取 IP 后 NAPT 可以继续工作」——AP 客户端此时可连 192.168.4.1 但无外网（无 captive portal 提示）

## 6. README 与代码的偏差（文档证据链污染，本工程最大坑）

README §20-§22 的命令行控制台、Web Server（`http://192.168.4.1`）、mDNS（`esp32-nat-router.local`）、ACL、PCAP 抓包、OLED/LED、MQTT/HA 特性——**main.c 中一行都没有**。这些日志 transcript 的 TAG（`ESP32 NAT router:`、`custom_dhcps:`）全部来自 martin-ger/esp32_nat_router 固件，作者显然先实测了上游固件再写精简版，但 README 没有分离两套证据链。

| 需求 | 正确选择 |
|---|---|
| 最小 IDF5 APSTA+NAT 骨架、自己加业务 | 本工程（586 行可读性极佳） |
| 开箱即用 Web 控制台改 SSID/信道/ACL | 直接用 martin-ger/esp32_nat_router |

另：README「当前测试配置」明文提交了真实上级 Wi-Fi 的 SSID+密码（作者自己加了"不要这样"的警示但密码没删）——公开仓库泄密的标准样本。

## 7. 性能边界（README 注意事项转写 + 调优点）

ESP32-S3 不是专用路由芯片，实际吞吐受：Wi-Fi 信号质量 / CPU 负载 / NAPT 转发开销 / TCP-UDP 流量类型 / lwIP 配置 / Wi-Fi 缓冲区 / AP 客户端数 影响。可调项：

- `CONFIG_LWIP_TCPIP_RECVMBOX_SIZE`（本工程 32，吞吐不足先加）
- Wi-Fi 缓冲：`CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM` / `CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM`（menuconfig 搜 WIFI）
- `CONFIG_LWIP_MAX_LISTENING_TCP`（下游 TCP 并发）
- 量级预期：ESP32 系 NAT 实测吞吐通常在个位数 Mbps 量级（手册无官方承诺值；以上为社区经验，以实测为准），够 IoT/网页，不够视频

## 8. 可复用模式

1. **两调用路由器**：`set_default_netif(STA)` + `napt_enable(AP)` 是整个"路由器"——先跑通再谈优化
2. **AP 先活**：30s 有限等 STA + 无条件开 NAPT，保证设备永远可从 192.168.4.1 侧触达
3. **sdkconfig.defaults 只放必要差异**（5 行），完整 sdkconfig 不手写
4. 空密码→`WIFI_AUTH_OPEN` 的 fallback 分支，是「开放热点」需求的标准写法
5. `ESP_EVENT_ANY_ID` 挂 WIFI_EVENT + 两个 IP_EVENT，是 APSTA 最小事件面

## 9. 坑位索引

坑 #166–173（known-pitfalls.md「Wi-Fi NAT 中继类」）：README 特性虚标证据链污染 / 真实密码入库 / NAPT sdkconfig 漏配 / 默认接口顺序 / 信道跟随 / 无限重连语义 / 空密码静默开放 / AP 可连无外网。

关联文档：wifi-networking.md（STA/AP/MQTT 基础）、production-readiness.md（吞吐与缓冲调优）、esp-idf-basics.md（事件循环与 netif 基础）。
