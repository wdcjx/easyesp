# ESP32-CAM 双机协处理：WiFi 摄像头桥接 STM32 主控

> 何时读：用户要 ESP32-CAM（esp32-camera）、摄像头抓帧/网页视频流、ESP32 与 STM32/其他 MCU 串口桥接组网、SoftAP 现场控制台、或问"摄像头模块怎么接/为什么用 Huge APP 分区"时读。
> 状态：知识沉淀（源自用户提供的已上板工程 stm32-car-project——传智杯智能小车，STM32F103 实时域 + ESP32-CAM 连接域；源工程在真实硬件运行，本文为源码转写、未二次复测；API 对齐 arduino-esp32 官方 CameraWebServer 示例族，2.x/3.x 通用面，细节以官方文档为准）。

## 1. 系统定位与双机架构

"STM32 管实时、ESP32 管连接"的协处理器模式：主控 MCU 保留实时控制（PWM/传感器时序），ESP32-CAM 补上 WiFi+摄像头+Web 台，两芯 UART 对接。与 xiaozhi（ESP32 一体机）相反，这是**瘦连接网关**范式。

| 域 | 芯片 | 职责 | 关键外设 |
|---|---|---|---|
| 实时域 | STM32F103 @72MHz（标准外设库） | 四电机 TB6612×2、舵机 TIM4、DHT11/MQ135/HC-SR04、OLED | TIM1/TIM3 72kHz PWM、USART1 PA9/PA10 |
| 连接域 | ESP32-CAM（AI-Thinker，经典 esp32 + PSRAM） | SoftAP + WebServer 控制台、OV2640 抓帧伪视频流、命令桥接、闪光灯 GPIO4 | camera（DVP 并口）、UART2 GPIO14/15、WebServer 80 |

流量模型：控制下行 = 浏览器 `/control?cmd=F` → ESP32 单字符 UART → STM32 立即执行并回 `ACK:*`；遥测上行 = STM32 每 3s `SENSOR:t,h,gas,dist\n` → ESP32 解析进全局变量 → 浏览器每 2s `/sensor` JSON 拉取；视频 = 浏览器每 250ms GET `/camera` JPEG。三条流全走单 loop 轮询，无 RTOS 任务。

## 2. ESP32-CAM（AI-Thinker）硬件事实表

| 资源 | 引脚/参数 | 说明 |
|---|---|---|
| 摄像头并口 | PWDN=32, XCLK=0, SIOD=26(SCCB SDA), SIOC=27, Y2=5, Y3=18, Y4=19, Y5=21, Y6=36, Y7=39, Y8=34, Y9=35, VSYNC=25, HREF=23, PCLK=22 | RESET=-1；34/35/36/39 input-only 全被吃掉 |
| 闪光灯 LED | GPIO4（宏 `LED_GPIO_NUM`） | 高电平亮；与用户代码自定义灯光同名宏冲突需 `#undef LED_GPIO_NUM` |
| SD 卡 | GPIO2/4/14/15（SD_MMC） | **与 UART2(14/15) + 闪光灯(4) 互斥**——本工程 SD 永不可用 |
| 本工程 UART2 | RX=GPIO14, TX=GPIO15 | `HardwareSerial SerialSTM32(2)`；GPIO15 是 strapping（MTDO，boot 时输出日志），对端看到开机毛刺属正常 |
| PSRAM | 必须有（4MB） | 无 PSRAM 降级 SVGA/fb1，伪视频流勉强能跑但慢；板型选 ESP32 Wrover Module |
| 分区 | **Huge APP (3MB No OTA/1MB SPIFFS)** | camera Web UI 或 esp_camera 本体吃 app 空间；普通 1.2MB 分区直接链接失败/放不下 |
| 供电 | 5V ≥ 2A | WiFi+摄像头峰值电流大，USB 口供电不足必现 brownout 复位 |

## 3. 摄像头初始化范式（Arduino 轨，esp32-camera）

源代码顺序：**摄像头先于 WiFi**（先把并口/LEDC 资源占住）。核心序列（全字段照抄可编译）：

```cpp
#include "esp_camera.h"
// #include "board_config.h" → 定义 CAMERA_MODEL_AI_THINKER 后 include camera_pins.h
#undef LED_GPIO_NUM   // 避免与自定义灯光宏撞名（GPIO4）

camera_config_t config = {};
config.ledc_channel = LEDC_CHANNEL_0;   // ⚠ XCLK 用 LEDC 生成，ch0/timer0 被占
config.ledc_timer   = LEDC_TIMER_0;
config.pin_d0..d7   = Y2..Y9_GPIO_NUM;  // 逐脚赋值
config.pin_xclk = XCLK_GPIO_NUM;  config.pin_pclk = PCLK_GPIO_NUM;
config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
config.pin_sscb_sda = SIOD_GPIO_NUM; config.pin_sscb_scl = SIOC_GPIO_NUM;
config.pin_pwdn = PWDN_GPIO_NUM;  config.pin_reset = RESET_GPIO_NUM;
config.xclk_freq_hz = 20000000;         // 20MHz；OV2640 支持 16/20
config.pixel_format = PIXFORMAT_JPEG;   // 传感器直出 JPEG，MCU 不编码
if (psramFound()) { config.frame_size = FRAMESIZE_UXGA; config.jpeg_quality = 10; config.fb_count = 2; }
else              { config.frame_size = FRAMESIZE_SVGA; config.jpeg_quality = 12; config.fb_count = 1; }
esp_err_t err = esp_camera_init(&config);           // != ESP_OK 要打日志并停止后续
sensor_t *s = esp_camera_sensor_get();
if (s->id.PID == OV2640_PID) { s->set_vflip(s,1); s->set_brightness(s,1); s->set_saturation(s,-2); }
s->set_framesize(s, FRAMESIZE_QVGA);                // init 后降到 QVGA 跑流
```

要点：UXGA 只是 fb 容量标定，实际跑流立即降到目标帧尺寸；`fb_count=2`（PSRAM）双缓冲抓取/发送并行；JPEG 品质 10（数字越小越好）。传感器 PID 判断用 `OV2640_PID`，改板换 OV3660/OV5640 时调节项不同。

## 4. WebServer 伪视频流（轮询 JPEG，不用 esp_http_server）

浏览器端 `setInterval(()=>{img.src='/camera?'+Date.now()},250)`，服务端整帧 JPEG 应答——约 4fps 的" MJPEG-lite"：

```cpp
void handleCamera() {
  camera_fb_t *fb = esp_camera_fb_get();          // 取一帧（阻塞至帧就绪）
  if (!fb) { server.send(500, "text/plain", "Camera capture failed"); return; }
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "no-cache");
  server.send_P(200, PSTR("image/jpeg"), (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);                        // ⚠ 必须归还，否则 fb 池耗尽黑屏
}
```

| 方案 | 吞吐 | 复杂度 | 适用 |
|---|---|---|---|
| 轮询 JPEG（本工程） | ~4fps@QVGA，每个 `<img>` 独立请求 | 极低，WebServer 即可 | 单客户端监控、遥控视角 |
| esp_http_server multipart `/stream`（官方 CameraWebServer） | 25fps+ | 高（app_httpd.cpp 24KB） | 多客户端流畅视频 |
| WebSocket 推帧 | 中 | 中 | 与控制信令同通道时 |

选轮询的隐性代价：`send_P` 在 loop 线程里同步发整帧，期间 `/control` 控制命令排队——车在视频加载时会"卡半拍"（坑 #165）。多标签页同开时 fb 争用加剧。

## 5. 跨 MCU UART 协议（两端对照）

物理：ESP32 TX15 → STM32 RX PA10，ESP32 RX14 ← STM32 TX PA9，**必须共地**（源 README 未提示，坑 #163）。115200 8N1。

| 方向 | 帧 | 语义 | 生成端代码 |
|---|---|---|---|
| 下行 | 单字符，**无换行** | `F`前进 `B`后退 `L`左 `R`右 `S`停 `G`抓取 `A`松开（另有 `D` 请求立即上报） | `SerialSTM32.write(cmd[0])`（Web `/control?cmd=`） |
| 上行 | `SENSOR:25,50,85,100.0\n` | 温度℃,湿度%,气体 ADC,距离cm，每 3s | STM32 `sprintf("SENSOR:%d,%d,%d,%.1f\n")` |
| 上行 | `ACK:FORWARD\n` 等 | 每命令一条回执（ESP32 只打日志不解析） | STM32 命令分发处 |
| 上行 | `ESP32 Ready\n` | ESP32 启动完成握手 | setup 末尾 |

下行单字符不带换行能工作，是因为 STM32 活代码用**轮询逐字符立即执行**（见 §6）；换行协议版（`X\n` 才执行）是死代码。两端协议假设不一致是隐形雷（坑 #156）。

上行解析（ESP32 侧，Arduino String 手法）：

```cpp
while (SerialSTM32.available()) {
  String line = SerialSTM32.readStringUntil('\n');  // ⚠ 默认 1000ms 超时（坑 #154）
  parseSTM32Data(line);                              // startsWith("SENSOR:") + 3 次 indexOf(',') + substring().toInt()/toFloat()
}
```

## 6. 死代码与协议漂移实证（本工程最大教学价值）

同一仓库里 STM32 侧有**两套 UART 实现**，活的是轮询版：

| | `USER/main.c`（活） | `HARDWARE/UART/uart_comm.c`（死） |
|---|---|---|
| 接收方式 | 主循环轮询 `USART_GetFlagStatus(RXNE)`，任何非 `\r\n` 字符**立即**执行 | RXNE 中断 + 64B 行缓冲，收满 `X\n` 才执行 |
| 中断 | 未开（USART1_IRQHandler 永不触发） | NVIC 配好但从未被 main 调用 |
| 上行格式 | `SENSOR:%d,%d,%d,%.1f\n` CSV | `SENSOR:{"temp":25,...}\n` JSON |
| `A` 命令 | `Servo_Release()`（松开），ACK 却写 `ACK:AUTO_TRACK` | `CMD_AUTO_TRACK`（自动追踪） |

后果推演（未上板验证的静态结论）：若有人把死代码接回去，JSON 行到 ESP32 的 `substring().toInt()` 会把 `{"temp":25` 解析成 0——**两套协议共存即数据清零**（坑 #155）；ACK 文案 `AUTO_TRACK` 泄露了从旧版复制粘贴的痕迹（坑 #157）。ESP32 侧死代码：`app_httpd.cpp`（24KB）+ `camera_index.h`（**147KB** gzipped 官方 Web UI）+ `ci.json` 原样躺在 sketch 目录，`startCameraServer()` 从未被调用（坑 #158）；`partitions.csv` 放 sketch 目录**不生效**，分区靠 IDE 菜单选 Huge APP（坑 #159）。教训：从官方示例起步时，没用的文件要么删、要么挪库目录，别让"参考物"长成"协议竞争者"。

## 7. 纪律对照（源工程 vs 本技能铁律）

| 源工程做法 | 本技能纪律 | 差距 |
|---|---|---|
| `readStringUntil('\n')` 在 available 循环里，默认 1000ms 超时 | 等待必须带超时且不阻塞事件循环 | 半行数据可把 WebServer 饿 1s（坑 #154） |
| AP 失败 `while(1) delay(1000)` | 失败要可观测/可恢复 | 停机无指示（坑 #161） |
| SSID/密码硬编码进 .ino | 凭据入 NVS/配置 | 教学工程可接受 |
| loop 尾 `delay(1)` 让出 | ✔ 符合 |
| fb 用后 `esp_camera_fb_return` | ✔ 正确（漏掉则黑屏死流） |
| camera 先于 WiFi 初始化 | ✔ 正确（资源先占） |
| STM32 侧 PB3/PB4 当 GPIO 却未做 SWJ JTAG disable remap | 跨 MCU 审查发现：JTDO/NJTRST 默认占脚，右后轮方向脚可能无效（坑 #164，以原理图实测为准） |

## 8. 可复用模式

1. **职责切分表**：把"WiFi+摄像头+Web"整体搬到 ESP32-CAM，主控只留实时——任何 MCU 小车/机械臂可直接套。
2. **单字符命令协议**：`/control?cmd=X` → UART 单字符 → ACK 回执，30 行实现双向闭环；扩展位靠字符表（本表 8 命令）。
3. **`SENSOR:CSV` 遥测行**：逗号分隔 + 行结尾，解析端 `indexOf/substring` 十行搞定；胜过 JSON（MCU 端拼串贵）。
4. **伪 MJPEG 轮询**：时间戳防缓存 + `Cache-Control:no-cache` + `fb_get/fb_return` 三件套，不引 esp_http_server。
5. **AP 现场控制台**：SoftAP + 内网 IP 192.168.4.1 + 单页 HTML（R"rawliteral" 内嵌），零外部依赖部署。
6. **XCLK 代价意识**：esp32-camera 的 20MHz XCLK 由 LEDC ch0/timer0 合成——后续 PWM/`analogWrite` 必须避开这两个通道（坑 #160）。

## 9. 坑位索引

坑 #154–165 属本档：#154 readStringUntil 阻塞饿死 / #155 双实现协议漂移 / #156 无换行依赖立即执行 / #157 'A' 语义漂移 / #158 147KB 死代码 / #159 分区表文件惰性 / #160 XCLK 占 LEDC0+宏撞名 / #161 while(1) 停机 / #162 SD 与 UART2 引脚互斥+strapping / #163 跨板共地 / #164 PB3/PB4 SWJ remap / #165 单线程大响应阻塞控制。
