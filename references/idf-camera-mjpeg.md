# ESP32-S3 摄像头图传（IDF 轨 esp32-camera + esp-wifi-connect + MJPEG 流）

> 何时读：用 **ESP-IDF**（不是 Arduino）接 OV2640/OV5640 做网页图传、配网、MJPEG 流；或需要把 Arduino 版 CameraWebServer 迁到 IDF 组件模型。
> 状态：知识沉淀（源工程 esp-idf-camera 已上板；API 对齐 ESP-IDF 5.5.x / espressif/esp32-camera 2.x 官方文档）

## §1 定位与事实表

| 项 | 值 |
|---|---|
| 源工程 | esp-idf-camera（ESP-IDF 5.5.1，ESP32-S3-WROOM，OV2640） |
| 形态 | 单 URI MJPEG 网页流 + BOOT 键触发 AP 配网 + 蓝灯呼吸指示 |
| 组件 | `espressif/esp32-camera ^2.1.4`、`78/esp-wifi-connect ^3.0.2`、`zorxx/neopixel ^1.0.10` |
| 外设 | XCLK 15 / SCCB SDA 4 SCL 5 / D0–D7 11,9,8,10,12,18,17,16 / VSYNC 6 / HREF 7 / PCLK 13 |
| 帧参数 | VGA 640×480 JPEG q20，fb_count=2，PSRAM，GRAB_LATEST |
| 内存前提 | 4MB flash + PSRAM（fb 必须落 PSRAM） |

**与 Arduino 轨的分工**：Arduino 轨的 `CameraWebServer`（含 147KB 死代码、伪 MJPEG 轮询）见 `esp32cam-stm32-bridge.md`；本文是 **IDF 轨**：组件化、Kconfig 化、真 MJPEG（multipart/x-mixed-replace）。

## §2 工程结构

```
idf_camera/
├── main/
│   ├── main.cc            218 行  app_main + cameraInit + WiFi 事件
│   ├── httpd.cc           184 行  MJPEG 流 handler + 启停
│   ├── CMakeLists.txt     SRCS main.cc httpd.cc
│   └── idf_component.yml  三个托管组件
├── sdkconfig.defaults     CPU240 / 4MB QIO 80M / PSRAM 80M / FREERTOS_HZ=1000
└── sdkconfig              camera 专属 Kconfig
```

CMakeLists 关键行：

```cmake
idf_component_register(SRCS "main.cc" "httpd.cc"
                       PRIV_REQUIRES nvs_flash esp_psram esp_http_server esp_timer
                       REQUIRES cxx)
```

`sdkconfig` 里真正影响能否出图的四项：

| 配置 | 值 | 作用 |
|---|---|---|
| `CONFIG_OV2640_SUPPORT` | y | 传感器驱动编入（换 OV5640 要另开） |
| `CONFIG_SCCB_HARDWARE_I2C_DRIVER_NEW` | y | 用新 i2c 驱动跑 SCCB |
| `CONFIG_SCCB_HARDWARE_I2C_PORT1` | y | **SCCB 走 I2C 控制器 1** |
| `CONFIG_CAMERA_DMA_BUFFER_SIZE_MAX` | 32768 | 大 DMA 缓冲，高分辨率必需 |

其余：`CONFIG_CAMERA_TASK_STACK_SIZE=4096`、`CONFIG_CAMERA_CORE0=y`、`CONFIG_SCCB_CLK_FREQ=100000`、`CONFIG_CAMERA_JPEG_MODE_FRAME_SIZE_AUTO=y`。

> ⚠️ 上表 PORT1 与代码里 `camera_config_t.sccb_i2c_port = 0` **不一致**——见坑 #188。以配置为准时把结构体改成 `1`，反之亦然，**两处必须同一控制器**。

## §3 初始化序列

```c
void app_main(void) {
    if (!cameraInit()) return;      // 失败即返回，无重试
    if (!startWiFiConfig()) return; // 失败即返回
    xTaskCreatePinnedToCore(blinkBlueBreathingTask, "blink", 4096, NULL, 1, NULL, 1);
    xTaskCreatePinnedToCore(wifiConfigButtonTask,    "btn", 16384, NULL, 2, NULL, 1);
}
```

`cameraInit()` 内部顺序（顺序错就黑屏）：

1. `heap_caps_get_total_size(MALLOC_CAP_SPIRAM) == 0` → 直接报错返回（fb 落 PSRAM 的前提）
2. `esp_event_loop_create_default()`（esp-wifi-connect 的事件依赖它）
3. 填 `camera_config_t` → `esp_camera_init(&config)` 检查 `ESP_OK`
4. `sensor = esp_camera_sensor_get()` → `set_vflip(1)` / `set_brightness(1)` / `set_saturation(0)`

`camera_config_t` 字段（与 Arduino 版一一对应）：

| 字段 | 值 | 备注 |
|---|---|---|
| pwdn_io / reset_io | -1 / -1 | 模块无此脚 |
| xclk_io | 15 | 必须与模块丝印一致 |
| sccb_sda/scl | 4 / 5 | AS5600 等别共用 |
| d7…d0 | 16,17,18,12,10,8,9,11 | 顺序即 d7→d0，错一位图像花屏 |
| vsync/href/pclk | 6/7/13 | |
| xclk_freq_hz | 24 MHz | OV2640 常用 20/24M |
| ledc_timer/channel | LEDC_TIMER_0 / LEDC_CHANNEL_0 | **XCLK 占用 LEDC0**，用户 PWM 另选（坑 #160） |
| pixel_format | PIXFORMAT_JPEG | 走硬件 JPEG，省 CPU |
| frame_size | FRAMESIZE_VGA | 流式首选 VGA，UXGA 会挤爆 DMA |
| jpeg_quality | 20 | 越小越清晰越慢（0–63） |
| fb_count | 2 | 双缓冲，网络慢时丢旧帧 |
| fb_location | CAMERA_FB_IN_PSRAM | 无 PSRAM 必须改 DRAM 并降分辨率 |
| grab_mode | CAMERA_GRAB_LATEST | 实时优先 |
| sccb_i2c_port | 0 | 与 Kconfig PORT1 冲突，见坑 #188 |

## §4 AP 配网（esp-wifi-connect 三件套）

| 对象 | 用法 |
|---|---|
| `WifiStation` | STA 连接与控制 |
| `SsidManager` | 已存 SSID 列表（NVS） |
| `WifiManager::GetInstance()` | 统一调度 + 事件回调 |

```c
auto cfg = WifiManagerConfig();          // 可链式 Set...
cfg.ssid_prefix = "ESP32摄像头1";         // 配网热点名
cfg.language   = "zh-CN";
WifiManager::GetInstance().SetWifiManagerConfig(cfg)
    .SetEventCallback([](WifiEventType type, const std::string& data) {
        switch (type) {
        case WifiEventType::Connected:      should_blink_blue = false; startCameraServer(); break;
        case WifiEventType::Disconnected:   stopCameraServer(); break;
        case WifiEventType::ConfigModeExit: esp_restart(); break;   // 配网完成重启
        }
    }).Init();
if (SsidManager::GetInstance().GetSsidList().empty())
    WifiManager::GetInstance().StartConfigAp();   // 192.168.4.1 网页配网
else
    WifiManager::GetInstance().StartStation();
```

复位配网：BOOT（GPIO0）按下 → `stopCameraServer()` → `StopStation()` → `StopConfigAp()` → `ssid_manager->Clear()` → `StartConfigAp()`。按键用 50ms 二次读消抖。

NVS 初始化要容错：`NO_FREE_PAGES` 或版本不符 → `nvs_flash_erase()` 后重试一次。

## §5 MJPEG 流式

三段式 chunk（顺序不能颠倒）：

```c
const char *boundary = "123456789000000000000987654321";
_STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
_STREAM_PART     = "Content-Type: image/jpeg\r\n"
                   "Content-Length: %u\r\n"
                   "X-Timestamp: %d.%06d\r\n\r\n";
// handler 每帧：
httpd_resp_send_chunk(req, _STREAM_BOUNDARY, ...);   // 分隔符
httpd_resp_send_chunk(req, part_buf, hlen);          // 段头
httpd_resp_send_chunk(req, (char*)jpg, jpg_len);     // JPEG
```

响应头：`Content-Type: multipart/x-mixed-replace;boundary=…`、`Access-Control-Allow-Origin: *`、`X-Framerate: 30`、`Cache-Control: no-cache, no-store`。

**节拍与自适应质量**（源工程实现，可直接抄）：

| 机制 | 实现 |
|---|---|
| 目标帧间隔 | `33333 µs`（30fps），每帧按剩余时间 `vTaskDelay` 补齐 |
| 每秒采样 | 统计实际帧耗时 |
| 变慢 | 帧时 > 1.5×目标 且 q>30 → `q -= 10` |
| 变快 | 帧时 < 0.7×目标 且 q<90 → `q += 5` |
| 非 JPEG 帧 | `frame2jpg(fb, 50, &buf, &len)` 转换后独立释放 |

> 注意：`frame2jpg` 的转换缓冲是 `malloc` 的，必须在发送后 `free`，且 `fb_return()` 不能漏。

## §6 启停与生命周期

| 项 | 实现 | 目的 |
|---|---|---|
| `httpd_start` | 重试 6 次、每次间隔 1s | WiFi 刚连上时端口可能未就绪 |
| `httpd_config_t` | port 80、max_uri_handlers 32（实际 1 个 URI） | 浪费但无害 |
| `stopCameraServer` | 另起 `asyncStopCameraServerTask` 调 `httpd_stop` | **不能在 WiFi 事件回调里 join**，否则事件任务被自己阻塞 |
| 流循环退出 | 取帧失败或发送失败 → break | 客户端需重连刷新 |

## §7 IDF 轨 vs Arduino 轨

| 维度 | Arduino（CameraWebServer） | IDF（本工程） |
|---|---|---|
| 摄像头驱动 | 内置库，配置写死 | 托管组件 + Kconfig |
| 配置 | `board_config.h` 宏 | `idf_component.yml` + `sdkconfig` |
| 配网 | 手写 SoftAP + 网页 | esp-wifi-connect 托管 |
| 流 | 轮询 JPEG（≈4fps 伪流） | 真 MJPEG multipart |
| XCLK | `ledcSetup` 经典 API | Kconfig + 新驱动 |
| 分区 | IDE 菜单 Huge APP | `sdkconfig.defaults` 指定 |

迁移要点：① `pixel_format` 保持 JPEG，别用 RGB565 走网络；② 分辨率与 `DMA_BUFFER_SIZE_MAX` 匹配；③ `esp_event_loop_create_default()` 必须早于 WiFi 组件初始化；④ 组件版本钉住（`^2.1.4` 会随上游飘）。

## §8 与既有文档的关系

- Arduino 轨 ESP32-CAM（引脚预算、伪 MJPEG、跨 MCU 串口）：`esp32cam-stm32-bridge.md`
- Wi-Fi 栈（STA/AP/事件机/OTA）：`wifi-networking.md`
- 引脚禁区（strapping/输入专用）：`gpio-pinout-guide.md`

## §9 坑位索引

| # | 一句话 |
|---|---|
| 188 | `sccb_i2c_port=0` 与 Kconfig `PORT1` 冲突 |
| 189 | `cameraInit()` 失败即 return，无重试无提示 |
| 190 | 只查 PSRAM 总量，未处理「有 PSRAM 但 fb 仍落 DRAM」的降级 |
| 191 | 自适应质量无下限回退，弱网画质塌陷 |
| 192 | 取帧失败直接退出流循环，客户端黑屏 |
| 193 | 单 URI 却配 `max_uri_handlers=32`，`ra_filter` 死代码 |

## 自检

- [ ] `camera_config_t.sccb_i2c_port` 与 `CONFIG_SCCB_HARDWARE_I2C_PORT*` 一致
- [ ] `esp_event_loop_create_default()` 早于 WiFi 组件
- [ ] PSRAM 检查 → 无 PSRAM 时降分辨率并改 `fb_location`
- [ ] `fb_return()` 与 `frame2jpg` 缓冲释放路径完备
- [ ] `httpd_stop` 不在事件回调上下文直接调用
