> 何时读：在 Arduino / ESP-IDF 两轨间做选择、搭建 Arduino IDE 或 PlatformIO 工程、查 core 3.x API 迁移差异、或在 sketch 里混用 FreeRTOS
> 状态：知识沉淀（未上板实测；API 对齐 arduino-esp32 3.x / ESP-IDF 5.3.x 官方文档）

# Arduino 轨（arduino-esp32 3.x）

## 1. 轨道选择

| 选 Arduino 轨 | 回 ESP-IDF 轨 |
|---|---|
| 原型 / 教学 / 竞赛赶工：setup+loop 即可开工，WiFi/HTTP 几行通 | 精细外设控制：新驱动（新 I2S/RMT/USB 等）先落在 IDF，Arduino 封装滞后或丢参 |
| 库生态：U8g2 / LovyanGFX / LVGL / Adafruit 系，Library Manager 一键装 | 低功耗定制：deep sleep / wifi 省电 / 电源管理的细粒度组合配置 |
| 迭代快：写→一键上传→串口监视，认知负担小 | 体积控制：menuconfig 裁剪、自定义分区表，Flash/RAM 预算紧张的量产件 |
| 直接复用海量 Arduino 示例与教程 | OTA / 分区 / bootloader 级定制；版本可锁定的可复现构建 |

## 2. 安装与工程形态

Arduino IDE 2.x：Boards Manager 搜 `esp32 by Espressif Systems` 安装 3.x（IDE 2.x 一般无需附加地址；老版本先加附加开发板 URL：https://espressif.github.io/arduino-esp32/package_esp32_index.json），再在 Tools→Board→esp32 选具体板。

PlatformIO（VSCode）platformio.ini 完整示例：
```ini
[env:esp32dev]
platform = espressif32      ; 官方平台钉的 core 版本可能滞后；需要 3.x 新特性时用社区分叉：
                            ; platform = https://github.com/pioarduino/platform-espressif32.git
framework = arduino
board = esp32dev            ; S3: esp32-s3-devkitc-1 ; C3: esp32-c3-devkitm-1
monitor_speed = 115200
upload_speed = 921600
build_flags =
    -DCORE_DEBUG_LEVEL=3    ; 日志级别 0~5：None/Error/Warn/Info/Debug/Verbose
```
core 具体版本以 PlatformIO 实际解析为准；不确定时查对应 Release Notes。

## 3. 程序模型

- 入口：setup() 执行一次，loop() 反复执行；二者由框架内置任务 loopTask 承载
- loopTask 默认：栈 8192 字节、优先级 1；双核芯片（esp32/S3）跑在 core 1，单核 C3 在 core 0
- core 0 上有 WiFi/协议栈等系统任务；重负载自建任务时用 xTaskCreatePinnedToCore 显式选核，避免与 loopTask 同核互卡
- loop() 内长忙等必须 delay()/yield()：(1) 不让出会饿死同核同优先级任务；(2) 启用 Task Watchdog 时持续不喂狗触发超时复位；delay() 即 vTaskDelay，阻塞让出 CPU
- 大栈需求（LVGL、深递归）不要硬塞 loop()，另建大栈任务（见第 6 节）

## 4. 2.x→3.x 迁移表（重点坑）

| 领域 | 2.x 写法 | 3.x 写法 |
|---|---|---|
| LEDC | ledcSetup(ch,freq,res); ledcAttachPin(pin,ch); ledcWrite(ch,duty) | ledcAttach(pin,freq,res); ledcWrite(pin,duty)；通道自动分配；ledcWriteTone(pin,freq) 出音调 |
| PWM | 无 analogWrite（需手工接 LEDC） | analogWrite(pin, 0..255) 原生（LEDC 实现）；analogWriteResolution(bits) 改分辨率 |
| USB 串口 | Serial=UART0 | Tools→USB CDC On Boot=Enabled 后 S3/C3 原生 USB 即 Serial；Disabled 则回 UART0 |
| hw_timer | timerBegin(num,div,countUp); timerAttachInterrupt(t,fn,edge); timerAlarmWrite | timerBegin(freq)（无定时器编号）；timerAttachInterrupt(t,fn)（无 edge 参数）；timerAlarm(t,value,autoreload,reload_count) |
| WiFi 事件 | ARDUINO_EVENT_* 枚举 | 不变（2.0.0 已由 SYSTEM_EVENT_* 改名，3.x 延续） |
| I2S/RMT/ADC | 旧封装 | 随 IDF 5.x 新驱动重写，封装差异以所用 core 版本 Release Notes 为准 |

所有签名差异的最终裁决：https://github.com/espressif/arduino-esp32/releases 各版迁移说明。

## 5. 常用能力 API 表

| 头文件 | 常用调用 |
|---|---|
| WiFi.h | WiFi.begin(ssid,pass) / WiFi.status()==WL_CONNECTED / WiFi.localIP() / WiFi.setAutoReconnect(true) / WiFi.setSleep(false)（降延迟、增功耗）/ WiFi.onEvent(cb, ARDUINO_EVENT_WIFI_STA_DISCONNECTED) / WiFi.scanNetworks() |
| WiFi.h（TCP） | WiFiServer server(80); server.begin(); server.available() 返回已连接 WiFiClient；client.connect(host,port) / print / read / stop |
| HTTPClient.h | http.begin(url); int code=http.GET(); code==HTTP_CODE_OK 再 http.getString(); https 需 WiFiClientSecure 且 setInsecure() |
| Preferences.h | NVS 键值，见下 |
| U8g2 / LovyanGFX / LVGL | 单色 OLED / 高速 LCD / 完整 GUI 框架；各查其文档 |

Preferences 最小用法：
```cpp
#include <Preferences.h>
Preferences prefs;
prefs.begin("cfg", false);              /* 命名空间；false=读写，true=只读 */
prefs.putUInt("count", 42);
uint32_t v = prefs.getUInt("count", 0); /* 第二参数为缺省值 */
prefs.remove("count");                  /* 删键 */
prefs.clear();                          /* 清整个命名空间 */
prefs.end();
```

## 6. sketch 里直接用 FreeRTOS

FreeRTOS.h/task.h 由 Arduino 环境自带（无需 include）；queue/信号量头建议显式引入。任务/队列/信号量即 IDF 原生 FreeRTOS：

```cpp
#include <Arduino.h>
#include "freertos/queue.h"

static QueueHandle_t q = nullptr;

void sensorTask(void *arg) {                 /* 常驻任务永不 return */
  const int pin = (int)(intptr_t)arg;
  for (;;) {
    int v = analogRead(pin);
    xQueueSend(q, &v, 0);                    /* 0：满则丢弃不等 */
    vTaskDelay(pdMS_TO_TICKS(100));          /* 10Hz 采样 */
  }
}

void setup() {
  Serial.begin(115200);
  q = xQueueCreate(16, sizeof(int));
  xTaskCreatePinnedToCore(sensorTask, "sensor", 4096,
                          (void *)(intptr_t)34,   /* 经典 esp32 的 ADC1 脚 34（仅输入）；S3/C3 引脚不同 */
                          2, nullptr, 0);         /* 优先级 2 钉在 core0；开 WiFi 时避免再压 core0 */
}

void loop() {
  int v;
  if (xQueueReceive(q, &v, pdMS_TO_TICKS(1000)))
    Serial.printf("adc=%d\n", v);
}
```
注意：IDF 版 FreeRTOS 中 xTaskCreate 系列的栈参数单位是字节（非原生 FreeRTOS 的字）。

## 7. IDF↔Arduino 概念映射

| ESP-IDF | Arduino |
|---|---|
| void app_main(void) | setup() + loop() |
| esp_err_t + ESP_ERROR_CHECK | bool/int 返回（true/正值为成功，无统一错误码族） |
| esp_log（ESP_LOGx） | Serial.printf + CORE_DEBUG_LEVEL 编译期级别 |
| nvs_flash + nvs_get/set | Preferences.h |
| ledc_channel_config 驱动 | ledcAttach/ledcWrite（3.x） |
| esp_timer | xTimer…；IDF 的 esp_timer 在 Arduino 内仍可直接调用 |
| esp_event 事件循环 | WiFi.onEvent(cb, ARDUINO_EVENT_X) |
| menuconfig | Tools 菜单固定预设（或 PlatformIO build_flags） |
| partitions.csv | Tools→Partition Scheme 预设 |
| idf.py flash / monitor | IDE 上传按钮 / 串口监视器 |

## 8. Arduino as ESP-IDF component

可行：官方文档提供把 arduino-esp32 作为 IDF 组件引入 CMake 工程的流程（app_main 里自行调 setup/loop）；但 core 与 IDF 版本须严格配对、维护成本高，非本 skill 默认推荐。

## 9. 烧录选项

| 项 | 位置 / 取值 | 要点 |
|---|---|---|
| Partition Scheme | Tools 菜单；默认 4MB（1.2MB APP/1.5MB SPIFFS） | OTA 选 Minimal SPIFFS (1.9MB APP with OTA)；大固件选 Huge APP；须按板上实际 Flash 选 |
| PSRAM | Tools→PSRAM Disabled/Enabled | S3 带 PSRAM 板（N8R8/N16R2 等）必开；影响大缓冲/LVGL |
| Upload Speed | Tools 菜单 | 烧录不稳降到 115200 |
| USB CDC On Boot | Tools 菜单 | S3/C3 原生 USB 一线供电+串口；开启后 Serial 即原生 USB |
| 串口监视器 | IDE 内置 | 波特率与 Serial.begin 一致；原生 USB 免驱 |
