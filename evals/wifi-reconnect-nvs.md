# 任务书：Wi-Fi 断网重连 + 参数存 NVS

> 何时读：技能评测用（见 evals/README.md），非面向最终用户的功能需求文档。
> 状态：静态测试输入。仅按本任务书实现，不引入任务书之外的假设。

## 需求（用户原话风格）

帮我写一个 ESP32（经典款，ESP-IDF）程序：连我家 Wi-Fi，SSID 和密码存到 NVS 里，
上电读 NVS 直接连；连不上就每 30 秒重试，最多重试 10 次还是不行就重启芯片。
另外连上之后把拿到的 IP 用 ESP_LOGI 打出来，每 5 分钟打一次心跳。

## 平台与约束

- 芯片：ESP32（经典）；框架：ESP-IDF 5.3.x + FreeRTOS。
- 单文件 main.c 即可；引脚表 + 头部 EASYESP MANIFEST V1（本任务无 GPIO）。
- 交付前自检：`python scripts/validate_esp_generated.py main.c` 必须 0 VIOLATION。

## 行为清单（人工核对）

1. NVS 先于 WiFi：`nvs_flash_init()`（含 NVS_NOT_FOUND → erase 重试）在任何
   `esp_wifi_init()` 之前。
2. SSID/密码经 `nvs_open`/`nvs_get_str` 读取；不存在时用编译期默认值并写回 NVS。
3. 事件驱动：STA_START→connect；GOT_IP→打 IP（`ESP_LOGI`，一次性）；DISCONNECTED→
   重试计数 +1，达 10 次调用 `esp_restart()`；计数用 static 局部或文件级变量。
4. 重试用 `vTaskDelay`/定时器，禁止阻塞 while 忙等；30s 间隔在事件处理器之外
   （处理器内不得 vTaskDelay 长阻塞）。
5. 心跳 5 分钟：独立任务循环（含 vTaskDelay），或 esp_timer 周期定时器回调内仅
   ESP_LOGI（无堆操作）。

## 必查规则（validator + 坑位）

- R10（WiFi 前必须有 NVS init）、R14（事件处理器内阻塞）、R8（周期路径堆操作）。
- 坑位：#80 段事件循环误删/重复注册；重连风暴（固定间隔无上限重启=坑位 #171 家族）。

## 判定

0 VIOLATION + 行为清单 5/5 = PASS；任何 VIOL 或清单缺项 = FAIL（记录到 ROADMAP）。
