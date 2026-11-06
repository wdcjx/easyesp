# Wi-Fi 与网络（STA/AP/ESP-NOW/MQTT/HTTP/OTA）

> 何时读：需要联网（STA）、自建热点（AP）、双机直连（ESP-NOW）、上云（MQTT/HTTP）或空中升级（OTA）时；§1 STA 铁律序列必读。
> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

## 1. STA 初始化铁律序列

顺序不可换；完整代码：

```c
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_log.h"

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();                                  // ① 只能在 START 事件后调用
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW("WIFI", "disconnect reason=%d",
                 ((wifi_event_sta_disconnected_t *)data)->reason);
        esp_wifi_connect();                                  // ② 无限立即重连（生产可改退避，见 §2）
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = (ip_event_got_ip_t *)data;    // ③ 拿到 IP 才算联网成功
        ESP_LOGI("WIFI", "ip=" IPSTR, IP2STR(&e->ip_info.ip));
    }
}

void wifi_start_sta(void) {
    esp_err_t e = nvs_flash_init();                          // 0. Wi-Fi 依赖 NVS（erase→retry 见 peripheral-recipes.md §9）
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        e = nvs_flash_init();
    }
    ESP_ERROR_CHECK(e);
    ESP_ERROR_CHECK(esp_netif_init());                       // 1. TCP/IP 协议栈
    ESP_ERROR_CHECK(esp_event_loop_create_default());        // 2. 默认事件循环
    esp_netif_create_default_wifi_sta();                     // 3. STA netif
    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();    // 4. 芯片默认初始化配置
    ESP_ERROR_CHECK(esp_wifi_init(&wcfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));

    wifi_config_t cfg = {
        .sta = {
            .ssid = "myssid",   // 动态赋值：strlcpy((char*)cfg.sta.ssid, s, sizeof(cfg.sta.ssid))
            .password = "mypassword",
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());                       // 5. 之后一切异步走事件，此处直接 return
}
```

事件驱动状态机：

```
esp_wifi_start()
  └► WIFI_EVENT_STA_START ──esp_wifi_connect()──► 关联中
        │ 802.11 关联成功                        │ 失败/掉线
        ▼                                        ▼
  WIFI_EVENT_STA_CONNECTED             WIFI_EVENT_STA_DISCONNECTED{reason}
        │ DHCP（数秒）                            │ esp_wifi_connect() 重连 → 回关联中
        ▼
  IP_EVENT_STA_GOT_IP ★ 联网成功（业务从此开始）
```

坑：CONNECTED ≠ 可通信（尚无 IP），socket/MQTT/HTTP 等 GOT_IP 再启；回调运行在事件任务（默认栈），勿长阻塞或 vTaskDelay。

## 2. 事件速查 / 断连原因码 / 重连策略

| 事件 | 含义 | 典型动作 |
|---|---|---|
| WIFI_EVENT_STA_START | 驱动就绪 | esp_wifi_connect() |
| WIFI_EVENT_STA_CONNECTED | 802.11 关联成功（无 IP） | 等 DHCP |
| WIFI_EVENT_STA_DISCONNECTED | 断开（含首次连接失败） | 读 reason，重连 |
| IP_EVENT_STA_GOT_IP | 拿到 IP/掩码/网关 | 启动网络业务 |

高频 reason 码（`wifi_event_sta_disconnected_t.reason`，wifi_err_reason_t）：

| 码 | 宏 | 排查 |
|---|---|---|
| 201 | WIFI_REASON_NO_AP_FOUND | 扫不到 AP：SSID 错/信号弱/隐藏 SSID |
| 2 | WIFI_REASON_AUTH_EXPIRE | 认证超时：密码错或 AP 拒绝 |
| 15 | WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT | 四次握手超时：密码错误典型码 |
| 200 | WIFI_REASON_BEACON_TIMEOUT | AP 失联：掉电/距离/干扰，等自动重连 |
| 8 | WIFI_REASON_ASSOC_LEAVE | 本端主动断开（esp_wifi_disconnect/休眠） |

重连：DISCONNECTED 里直接 `esp_wifi_connect()` = 无限立即重连（调试推荐）；生产用软定时器退避（1s→2s→…→60s 封顶，模式见 peripheral-recipes.md §2），勿在事件回调里 delay 阻塞 WiFi 任务。

## 3. AP 模式 / SoftAP+STA 共存

```c
void wifi_start_ap(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();              // AP netif + 内置 DHCP 服务器（192.168.4.1/24）
    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wcfg));

    wifi_config_t cfg = {
        .ap = {
            .ssid = "mydev",
            .ssid_len = strlen("mydev"),
            .channel = 1,
            .password = "12345678",                  // WPA2 最短 8 字节
            .max_connection = 4,
            .authmode = WIFI_AUTH_WPA2_PSK,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());               // AP 启动即广播，无需 connect
}
```

- APSTA：`esp_wifi_set_mode(WIFI_MODE_APSTA)`，且 `esp_netif_create_default_wifi_ap()` 与 `esp_netif_create_default_wifi_sta()` 都要建；STA 侧另走 §1。共用射频，吞吐减半（典型行为）。
- AP 事件：WIFI_EVENT_AP_STACONNECTED / AP_STADISCONNECTED（client MAC）；IP_EVENT_AP_STAIPASSIGNED（分给 client 的 IP）。
- 坑：WPA2 密码 <8 字节则 `esp_wifi_set_config` 失败；开放网络 authmode=WIFI_AUTH_OPEN、不设 password。

## 4. ESP-NOW

```c
#include "esp_now.h"
#include "esp_wifi.h"

static volatile bool s_rx_flag;
static uint8_t s_rx_mac[6], s_rx_buf[250];
static int s_rx_len;

static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
    /* 回调在 WiFi 任务上下文：只拷贝+置标志，长处理转主任务 */
    memcpy(s_rx_mac, info->src_addr, 6);
    s_rx_len = len < (int)sizeof(s_rx_buf) ? len : (int)sizeof(s_rx_buf);
    memcpy(s_rx_buf, data, s_rx_len);
    s_rx_flag = true;
}
static void on_send(const uint8_t *mac, esp_now_send_status_t st) {
    /* st == ESP_NOW_SEND_SUCCESS / ESP_NOW_SEND_FAIL */
}

void espnow_init(void) {
    // 前置：Wi-Fi 已按 §1 初始化到 esp_wifi_start()（STA 模式，无需连接成功）
    ESP_ERROR_CHECK(esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE));  // 双方固定同信道
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(on_recv));
    ESP_ERROR_CHECK(esp_now_register_send_cb(on_send));

    uint8_t peer_mac[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };     // 广播
    esp_now_peer_info_t peer = { .channel = 0, .ifidx = WIFI_IF_STA }; // channel=0 跟随当前信道
    memcpy(peer.peer_addr, peer_mac, 6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
}

int espnow_send(const uint8_t mac[6], const uint8_t *d, int n) {  // n ≤ ESP_NOW_MAX_DATA_LEN(250)
    return esp_now_send(mac, d, n);
}
```

坑：先 `esp_wifi_start()` 再 `esp_now_init()`（STA 模式即可，不必连上路由器）；单包上限 250 字节，更大自己分包；默认不加密不重传，广播丢包需上层容忍/重发；改信道先 `esp_now_del_peer()` 再重加。

## 5. MQTT（espressif/mqtt 组件）

`main/idf_component.yml`：

```yaml
dependencies:
  espressif/mqtt: "^1.0"
```

```c
#include "mqtt_client.h"

static esp_mqtt_client_handle_t s_mq;

static void on_mqtt(void *arg, esp_event_base_t base, int32_t id, void *data) {
    esp_mqtt_event_handle_t e = data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        esp_mqtt_client_subscribe(s_mq, "dev/cmd", 1);
        esp_mqtt_client_publish(s_mq, "dev/stat", "online", 6, /*qos*/1, /*retain*/0);
        break;
    case MQTT_EVENT_DATA:   // e->topic/topic_len、e->data/data_len 非 0 结尾，用 "%.*s"
        break;              // 大消息分片：e->current_data_offset / e->total_data_len
    case MQTT_EVENT_DISCONNECTED:
        break;              // 组件内置自动重连（reconnect_timeout_ms 默认 10s）
    default:
        break;
    }
}

void mqtt_start(void) {     // 前提：已 IP_EVENT_STA_GOT_IP（§1）
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = "mqtt://broker.emqx.io:1883",
        .broker.address.transport = MQTT_TRANSPORT_OVER_TCP,
        .credentials.username = "user",
        .credentials.client_id = "esp32-01",
        .session.keepalive = 30,
        .buffer.size = 1024,           // 收缓冲；发缓冲 .buffer.out_size
    };
    s_mq = esp_mqtt_client_init(&cfg);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(s_mq, ESP_EVENT_ANY_ID, on_mqtt, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(s_mq));
}
```

坑：`esp_mqtt_client_publish` 返回 msg_id（>0 排队成功，-1 失败）；payload 超 buffer.size 时 DATA 分片到达（按 total_data_len 拼包）；仅当 broker 地址等 CONFIG 变化才 `esp_mqtt_client_stop()` → `esp_mqtt_client_destroy()` 后重建，destroy 前必须 stop；TLS 用 `mqtts://` + `.broker.verification.certificate`（以官方文档为准）。

## 6. HTTP 客户端（esp_http_client）

```c
#include "esp_http_client.h"
#include "esp_log.h"

esp_err_t http_get(const char *url) {
    esp_http_client_config_t cfg = { .url = url, .timeout_ms = 10000 };  // 连接/读超时
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    esp_err_t err = esp_http_client_perform(c);           // 阻塞至完成
    if (err == ESP_OK)
        ESP_LOGI("HTTP", "status=%d len=%d",
                 esp_http_client_get_status_code(c),
                 esp_http_client_get_content_length(c));
    esp_http_client_cleanup(c);                          // 必须 cleanup，否则句柄/内存泄漏
    return err;
}

esp_err_t http_post_json(const char *url, const char *body) {
    esp_http_client_config_t cfg = { .url = url, .timeout_ms = 10000 };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    esp_http_client_set_method(c, HTTP_METHOD_POST);
    esp_http_client_set_header(c, "Content-Type", "application/json");
    esp_http_client_set_post_field(c, body, strlen(body));  // Content-Length 自动设置
    esp_err_t err = esp_http_client_perform(c);
    esp_http_client_cleanup(c);
    return err;
}
```

坑：`perform` 一次性收整个 body 进 RAM，大文件用 `esp_http_client_open()` + `esp_http_client_read()` 流式；HTTPS 需 `.cert_pem`；流式回调挂 `cfg.event_handler`（HTTP_EVENT_ON_DATA）；重定向默认自动跟随。

## 7. OTA（esp_https_ota + 双 app 分区 + 回滚）

分区表 `partitions.csv`（4MB flash 示例，两个 app 分区建议等大）：

```csv
# Name,   Type, SubType, Offset,  Size,   Flags
nvs,      data, nvs,     0x9000,  0x4000,
otadata,  data, ota,     0xd000,  0x2000,
phy_init, data, phy,     0xf000,  0x1000,
ota_0,    app,  ota_0,   0x10000, 1500K,
ota_1,    app,  ota_1,   ,        1500K,
```

证书嵌入：`main/CMakeLists.txt` 加 `EMBED_TXTFILES := ca.pem`，生成符号 `_binary_ca_pem_start/_end`（文件名中 `.`/`-` 变 `_`）。

```c
#include "esp_https_ota.h"
#include "esp_ota_ops.h"
#include "esp_system.h"

extern const uint8_t ca_pem_start[] asm("_binary_ca_pem_start");
extern const uint8_t ca_pem_end[]   asm("_binary_ca_pem_end");

esp_err_t ota_run(const char *url) {            // GOT_IP 后在自己的任务里跑，勿在事件回调里调用
    esp_http_client_config_t hcfg = {
        .url = url,                              // https://host/firmware.bin
        .cert_pem = (const char *)ca_pem_start,
        .timeout_ms = 15000,
    };
    esp_https_ota_config_t ota_cfg = { .http_config = &hcfg };
    esp_err_t err = esp_https_ota(&ota_cfg);     // 阻塞：下载+校验+写 otadata
    if (err == ESP_OK) esp_restart();            // 重启进入新分区
    return err;
}

void ota_confirm(void) {                        // 新固件 app_main 自检通过后调用一次
    const esp_partition_t *run = esp_ota_get_running_partition();
    esp_ota_img_states_t st;
    if (esp_ota_get_state_partition(run, &st) == ESP_OK &&
        st == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();  // 确认正常，正式选定该分区
    }
    // 自检失败：esp_ota_mark_app_invalid_rollback_and_reboot() 回滚旧分区
}
```

要点：
- CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y 开回滚：新固件首启为 ESP_OTA_IMG_PENDING_VERIFY，未 confirm 即复位/看门狗 → bootloader 自动回滚旧分区。
- 下载中断/镜像校验失败时 otadata 未写，仍从旧分区启动，无需手工清理。
- 两 app 分区各 ≥ 固件最大体积；纯 http 固件源需放开校验配置（示例工程 CONFIG_OTA_ALLOW_HTTP），自担风险。

## 8. 网络内存水位

STA + 默认事件循环 + LWIP 启动后典型堆占用约 40–60KB（经验值标注，未实测校准；随 IDF 配置、加密方式、AMPDU 浮动，以板端 `esp_get_free_heap_size()` 实测为准）：

- 大缓冲（JSON/图像/大 payload）放 PSRAM：CONFIG_SPIRAM + `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)`；DMA 与网络驱动内部缓冲仍走内部 RAM。
- 优化前先量基线：`esp_get_free_heap_size()` / `esp_get_minimum_free_heap_size()`。
- 低内存先兆：socket 创建返回 ENOMEM、MQTT 启动失败、Wi-Fi 初始化 abort。

## 9. Arduino 映射（细节见 arduino-track.md）

| 任务 | ESP-IDF | arduino-esp32 3.x |
|---|---|---|
| STA 连接 | §1 铁律序列 | WiFi.begin(ssid, pass)；WiFi.status()==WL_CONNECTED 等价 GOT_IP |
| Wi-Fi 事件 | esp_event_handler_register | WiFi.onEvent(cb, ARDUINO_EVENT_WIFI_STA_DISCONNECTED 等) |
| AP | WIFI_MODE_AP | WiFi.softAP(ssid, pass) / WiFi.softAPConfig() |
| ESP-NOW | esp_now_* | 同名 API 直接可用（先 WiFi.mode(WIFI_STA)） |
| MQTT | espressif/mqtt | PubSubClient（默认缓冲 256B，大 payload 需 client.setBufferSize()） |
| HTTP | esp_http_client | HTTPClient：begin(url)/GET()/getString()；HTTPS 配 WiFiClientSecure |
| OTA | esp_https_ota | ArduinoOTA（网络烧录）或 Update 类（写 flash 分区） |
| NVS | nvs_* | Preferences |
| 堆内存 | esp_get_free_heap_size() | ESP.getFreeHeap() |
