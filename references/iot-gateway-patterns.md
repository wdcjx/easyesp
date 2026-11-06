# IoT 网关模式（MQTT 生产化 · 配置管理 · 命令分发）

> 何时读：做"ESP32 当网关/设备端、MQTT 连服务器平台"的工程——多环境配置、MQTT 生产级连接与发布防御、命令下发分发、掉电回放、长周期心跳。简单 MQTT 收发直接看 wifi-networking.md §5 即可，不必读本文。
> 状态：实战项目沉淀（源自**已上板部署**的 yihong-iot GatewayESP32Client（ESP32-S3 实机运行、Arduino/PlatformIO），本文为源码审计转写、未在本机二次复测；API 对齐 arduino-esp32 2.x/3.x 共有子集，差异处逐条标注）

来源与适用性：

| 模式 | 一句话 | 适用 |
|------|--------|------|
| 三环境配置 | 构建宏选 `/config.{env}.json`，LittleFS 常驻 | 一套固件多环境（dev/test/prod）部署 |
| 连接编排 | DNS 诊断→TCP 探活→setServer→connect→订阅→上线通告 | 服务器域名不稳/需明确故障段 |
| 发布防御四连 | 双检+就地重连+长度预检+事后复查 | 不允许"假成功"丢数据的上报 |
| 溢出安全调度 | 无符号差值判周期，杜绝 49.7 天回绕停摆 | 任何 millis() 周期逻辑 |
| 兼容降级阶梯 | 同数据多 JSON 形态逐级退化 | 对端服务器解析能力不明 |
| NVS-TTL 缓存回放 | 命令 payload 存 Preferences，重启后回放 | 掉电续跑的外设回调命令 |
| 命令信封分发 | 统一信封 JSON + agreementType→handler | 多协议外设挂在同一网关 |

## 1. 三环境配置文件

```cpp
// platformio.ini: build_flags = -D ENV_PRODUCTION   （缺省回退 dev，见下方坑位）
#include <LittleFS.h>
#include <ArduinoJson.h>

StaticJsonDocument<4096> g_config;          // 常驻全局，一次加载；JsonDocument v7 写法见 §8

bool configLoad() {
    const char *path = "/config.dev.json";  // dev/test/prod 各一份，随 data/ 分区烧入
#if defined(ENV_PRODUCTION)
    path = "/config.prod.json";
#elif defined(ENV_TEST)
    path = "/config.test.json";
#endif
    if (!LittleFS.begin(true)) return false;             // true = 找不到就格式化
    File f = LittleFS.open(path, "r");
    if (!f) return false;
    DeserializationError err = deserializeJson(g_config, f);
    f.close();
    return err == DeserializationError::Ok;
}
// 类型化 getter 一律带兜底：缺键不崩，值可审计
String cfgStr(const char *key, const char *def = "") {
    return g_config[key] | def;               // v7 写法；v6 为 containsKey()+as<String>()
}
int32_t cfgInt(const char *key, int32_t def = 0) { return g_config[key] | def; }
```

config 字段模板（LittleFS data 分区）：

```json
{
  "mqtt":   { "server": "mqtt.example.com", "port": 1883, "username": "", "password": "",
              "subscribeTopic": "gateway_20559", "publishTopic": "gateway_server",
              "bufferSize": 2560, "maxMessageSize": 2048,
              "reconnectInterval": 5000, "connectionTimeout": 10000 },
  "device": { "id": "20559", "name": "gw-01", "type": "gateway", "firmwareVersion": "1.0.0" },
  "environment": "development"
}
```

纪律：配置只读不写——运行期改动走命令通道持久化到 NVS，不回写 JSON；无 schema 校验时，getter 兜底值就是全部防线，务必显式。

## 2. MQTT 生产连接编排

来源项目用 PubSubClient（`knolleary/PubSubClient@^2.8`）；IDF 轨用 esp-mqtt 的等价编排见 wifi-networking.md §5。Arduino 轨关键差异：PubSubClient 无事件回调，连接质量全靠主动编排。

```cpp
#include <PubSubClient.h>
WiFiClient g_net;               // 明文 1883；TLS 需 WiFiClientSecure + 证书/PSK（本文不展开）
PubSubClient g_mqtt(g_net);
char g_clientId[24];

void mqttSetup() {
    snprintf(g_clientId, sizeof(g_clientId), "esp32-%llX", ESP.getEfuseMac());
    uint16_t buf = (uint16_t)cfgInt("mqtt/bufferSize", 2560);
    g_mqtt.setBufferSize(buf);                       // 默认 256B！见坑 49
    g_mqtt.setServer(cfgStr("mqtt/server").c_str(), (uint16_t)cfgInt("mqtt/port", 1883));
    g_mqtt.setCallback(mqttOnMessage);               // std::bind 亦可用
}

// 连接前先确认"域名能解析、IP 能通 TCP"，把故障定位到段
bool mqttDiagnose() {
    IPAddress ip;
    if (!WiFi.hostByName(cfgStr("mqtt/server").c_str(), ip)) return false;  // DNS 段
    WiFiClient probe;
    probe.setTimeout(3000);                          // ms（3.x 语义），2.x 用 connect(ip, port) 阻塞语义
    if (!probe.connect(ip, (uint16_t)cfgInt("mqtt/port", 1883))) return false; // TCP 段
    probe.stop();
    // DNS 缓存陈旧场景：探活成功后直接 setServer(ip, port) 绕过域名，见坑 53
    return true;
}

bool mqttConnect() {
    if (g_mqtt.connected()) return true;
    if (!mqttDiagnose()) return false;
    bool ok = g_mqtt.connect(g_clientId,
                             cfgStr("mqtt/username").c_str(), cfgStr("mqtt/password").c_str());
    if (!ok) return false;
    g_mqtt.subscribe(cfgStr("mqtt/subscribeTopic").c_str());   // 命令下行
    g_mqtt.subscribe(("device/" + String(g_clientId) + "/status").c_str());
    String online = "{\"status\":\"online\",\"clientId\":\"" + String(g_clientId) + "\"}";
    g_mqtt.publish("device/connect", online.c_str());          // 上线通告
    return true;
}
```

重连纪律：主循环里未连接则按 `reconnectInterval`（ms）重试，勿写成 `while(!connect()) delay(5000);` 死等（阻塞 loop 饿死看门狗，对照 known-pitfalls #9）。

## 3. publish 防御四连

TCP 半开连接下 `connected()==true` 而 publish 实际丢失（服务器进程死了、NAT 超时、无 RST）。生产上报四步：

```cpp
bool mqttPublishSafe(const char *topic, const char *payload) {
    if (strlen(payload) + 128 > (size_t)g_mqtt.getBufferSize())   // ① 长度预检：超缓冲必截断，拒发
        return false;
    if (!g_mqtt.connected() && !mqttConnect())                    // ② 就地重连
        return false;
    bool sent = g_mqtt.publish(topic, payload);                   // QoS0：返回 true≠服务器已收
    if (!sent) { mqttConnect(); sent = g_mqtt.publish(topic, payload); }  // ③ 失败重连重发一次
    g_dirtyLink = g_dirtyLink || !sent;                           // ④ 置脏标志，下轮 loop 复查
    return sent;
}
```

QoS 说明：PubSubClient 默认 QoS0；要"确认送达"用 `publish(topic, payload, false)` 换 QoS1 需改库上限 `MQTT_MAX_PACKET_SIZE`/`MQTT_QOS`（以库文档为准）。真正不丢=应用层应答（guid 回执），见 §7。

## 4. 溢出安全周期调度

`millis()` 约 49.7 天回绕到 0。任何"绝对时间比较"（`if (millis() > lastBeat + 50000)`）在回绕点全错。统一写无符号差值：

```cpp
uint32_t tLastBeat = 0;
void loop() {
    uint32_t now = millis();
    if (now - tLastBeat >= HEARTBEAT_MS) {     // 无符号减法天然回绕安全
        tLastBeat = now;                        // 回绕点赋值同样安全
        sendHeartbeat();
    }
}
```

三个衍生纪律：①持久化 TTL 不要以 `millis()/1000` 为基准（回绕即错乱），用 `esp_timer_get_time()`（µs，int64，58 万年）或 RTC；②首连成功立即发一次心跳再起周期（`tLastBeat = millis() - HEARTBEAT_MS`）；③`String +=` 逐字节拼 payload 是 O(n²) 且堆碎片，payload 用预分配 `char[]` + `snprintf`。

## 5. 上行 JSON 服务器兼容（降级阶梯）

对端解析能力不明时：同一份心跳数据准备多级形态，失败逐级退化（本项目四级 full→hybrid→extended→serverCompatible）。通用化三条：

| 级 | 做法 |
|----|------|
| 1 | 完整嵌套（开发期自测用） |
| 2 | 减嵌套层数，数组改拼接字符串 |
| 3 | 平面键值（服务器最大兼容形态） |
| 4 | 序列化后 `deserializeJson` 回读验证再发——发出的就是服务器能解析的 |

空字段纪律：不确定对端是否容 null 时，`respCode="200"` 这类状态字段必填；`createTime/gatewayTime` 这类时间戳宁可 `null` 不填 `""`（空串会被当非法时间戳解析报错）。ArduinoJson 生成 null：`doc["gatewayTime"] = nullptr;`。

## 6. NVS-TTL 缓存与掉电回放

Preferences 封装 TTL 缓存（Arduino 轨 NVS 等价物；IDF 轨原生 nvs 见 peripheral-recipes.md §9）：

```cpp
#include <Preferences.h>
Preferences g_cache;

void cacheBegin() { g_cache.begin("cache_ns", false); }

void cachePut(const char *key, const String &val, uint32_t ttlSec) {
    g_cache.putString(key, val);
    if (ttlSec) g_cache.putULong((String("_expire_") + key).c_str(),
                                 (uint32_t)(esp_timer_get_time() / 1000000) + ttlSec);
}
String cacheGet(const char *key) {
    String ek = "_expire_" + String(key);
    if (g_cache.isKey(ek.c_str())) {
        uint64_t now = (uint64_t)(esp_timer_get_time() / 1000000);   // 秒，勿用 millis()/1000
        if (now >= g_cache.getULong(ek.c_str())) { g_cache.remove(key); g_cache.remove(ek.c_str()); return ""; }
    }
    return g_cache.getString(key, "");
}
```

掉电回放模式（外设回调命令）：收到 `startCallBack` 类命令时把整条命令 payload 原文 `cachePut`（TTL=回调时长）；重启后主循环读回、重新执行并构造响应。回放只对幂等命令安全（GPIO 置位类安全，脉冲计数类不安全）。

## 7. 命令信封与分发器

统一信封，一进多出。信封核心字段（本项目逐字）：

```json
{ "respCode": "200", "respMsg": "", "respEvent": "Event_HandleCommand",
  "guid": "原样透传", "toGatewayData": { "agreementType": "gpio",
  "parameter": "{...字符串化内嵌协议...}", "key": "open" },
  "toServerData": { "content": "open" } }
```

```cpp
void mqttOnMessage(char *topic, byte *payload, unsigned int len) {
    char buf[2048];
    if (len >= sizeof(buf)) return;                       // 长度预检
    memcpy(buf, payload, len); buf[len] = 0;              // 不逐字节 String +=（§4 纪律③）
    StaticJsonDocument<2048> req;                         // v7: JsonDocument req;
    if (deserializeJson(req, buf)) return;
    if (String((const char*)(req["respEvent"] | "")) != "Event_HandleCommand") return;  // 非命令丢弃

    const char *at = req["toGatewayData"]["agreementType"] | "";
    String parameter = req["toGatewayData"]["parameter"] | "";   // 注意：内嵌协议是字符串，需二次 deserialize
    if      (!strcmp(at, "gpio"))  handleGpio(parameter, req);
    else if (!strcmp(at, "rs485")) handleRs485(parameter, req);
    else if (!strcmp(at, "jc035")) handleJc035(parameter, req);
    // 响应：原信封回填 toServerData.content + respCode "200"/"500"，guid 原样返回
}
```

两条纪律：①`parameter` 是字符串化的 JSON（双重编码），拿到后二次 `deserializeJson`；②响应永远复用请求信封对象改字段，不要手工重建（guid/时间字段必须原样透传，服务器按 guid 对账）。

## 8. 依赖版本与迁移注意

| 项 | 现状 | 迁移 |
|----|------|------|
| ArduinoJson | 项目锁 v6（`DynamicJsonDocument/containsKey`） | v7 移除两者：`JsonDocument doc;`、`doc["k"].is<T>()`、`doc["k"] \| def`；新工程直接 v7 |
| PubSubClient | ^2.8，与 core 3.x 兼容 | `setBufferSize` 每实例独立堆分配，无 PSRAM 板计入预算 |
| platformio.ini | `platform=espressif32` 未锁版本 | 重装机拉新 platform 会跳 core 3.x/IDF5 直接编译失败——锁 `platform=espressif32@<x.y>`（本机未复现其构建，具体版本以官方 registry 为准） |
| S3 USB CDC | `ARDUINO_USB_MODE=1`+`ARDUINO_USB_CDC_ON_BOOT=1` | 3.x 仍有效；CDC 口烧录后 COM 号会变，enum 后重选 |
| 温度读数 | S3 上 `temperatureRead()` 语义未确认（项目用模拟值回避） | 以官方文档为准；不要拿经典 esp32 行为类推 |

## 9. 坑位索引

本文模式对应的实战坑见 known-pitfalls.md「实战项目类」：49（PubSubClient 256B 截断）、50（TCP 半开假成功）、51（millis 回绕）、52（深嵌套 JSON 被拒）、53（DNS 陈旧连不上）。BLE HID 键盘类见 36–42，飞控实时类见 43–48。
