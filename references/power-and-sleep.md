# 低功耗与睡眠

> 何时读：任务涉及电池供电、深睡/浅睡、唤醒源设计、功耗优化，或深睡后 IO/重启行为异常时读。
> 状态：知识沉淀（未上板实测；API/报文对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

## 1. 电源模式总表

| 模式 | RAM/RTC 保持 | CPU/外设 | 典型电流（手册典型值，以各芯片 datasheet 为准） | 进入 API | 唤醒后 |
|---|---|---|---|---|---|
| Active | 全部 | 全开 | CPU 数十 mA；WiFi TX 峰值 200mA 级 | 默认态 | — |
| Modem sleep（WiFi 省电） | 全部 | CPU 正常跑，射频按 DTIM 间歇睡 | 数十 mA | STA 连接后默认开启；esp_wifi_set_ps(WIFI_PS_MIN_MODEM/WIFI_PS_MAX_MODEM) | 透明，不中断 |
| Light sleep | DRAM＋RTC 全保持 | CPU 时钟停，外设时钟门控 | 数百 µA～1mA 量级 | esp_light_sleep_start() | 原地继续执行（不复位） |
| Deep sleep | 仅 RTC slow/fast mem（可配） | 全停；RTC 计时器/RTC GPIO/ULP（classic/S3）可活 | 约 10µA 量级 | esp_deep_sleep_start() | 等于复位，app_main 重跑 |
| Hibernate（S3/C3 等，最深档） | RTC 内存亦断 | 仅 RTC 定时器 | 约 5µA 级 | 深睡前 esp_sleep_pd_config() 关全部 RTC 域＋timer 唤醒（以 datasheet/官方文档为准） | 同深睡（复位） |

电流为 datasheet 手册典型值/量级，实测定多少是多少；ULP 运行时另计。

## 2. 深度睡眠完整范式

顺序：停外设 → 配唤醒源 → 收尾（hold/关 RTC 域）→ esp_deep_sleep_start()（不返回）。定时采集上传范式：

```c
void app_main(void) {
    // 深睡唤醒=冷启动，外设全部重新初始化
    bool from_timer = (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER);
    init_nvs_wifi_mqtt();                              // NVS/WiFi/MQTT 照常起（NVS 前置见 pitfall 26）
    read_sensor_and_publish();                         // 采集＋上传
    esp_wifi_stop();                                   // 收尾清单见 §5
    gpio_hold_en(GPIO_NUM_2);                          // 需要保持的输出
    gpio_deep_sleep_hold_en();                         // S3/C3 非 RTC 脚需要
    esp_sleep_enable_timer_wakeup(60ULL * 1000000);    // 60 s
    esp_deep_sleep_start();                            // 不返回
}
```

成本提示：深睡唤醒=全重启，WiFi/MQTT 重连耗时（秒级）且峰值电流大；周期太短（经验上 <30s 量级）可能比 light sleep 更费电，按占空比估算平均电流。

## 3. 唤醒源逐表（API 名以 5.3 esp_sleep.h 为准）

| 唤醒源 | API | 芯片 | 要点 |
|---|---|---|---|
| 定时器 | esp_sleep_enable_timer_wakeup(uint64_t us) | 全系 | RTC 计时；长周期精度受时钟源影响（%级，以 datasheet 为准） |
| EXT0（单 RTC GPIO 电平） | esp_sleep_enable_ext0_wakeup(gpio_num_t gpio, int level) | classic ESP32（S3 支持情况以头文件为准） | 仅 RTC IO：0/2/4/12–15/25–27/32–39 |
| EXT1（多 RTC GPIO 组合） | classic：esp_sleep_enable_ext1_wakeup(mask, ESP_EXT1_WAKEUP_ALL_LOW/ANY_HIGH)；S3 等 5.x 统一版：esp_sleep_enable_ext1_wakeup_io(mask, ESP_EXT1_WAKEUP_ANY_LOW/ANY_HIGH 等) | classic / S3 等 | classic mask 按 RTC IO 编号置位；唤醒脚查询 esp_sleep_get_ext1_wakeup_status()（S3 变体 esp_sleep_get_ext1_wakeup_status_io） |
| 数字 GPIO 深睡唤醒 | esp_deep_sleep_enable_gpio_wakeup(mask, ESP_GPIO_WAKEUP_GPIO_LOW/HIGH) | C3（仅 GPIO0–5）、S3 等 | C3 无 classic 式 EXT0/EXT1，走此 API；多脚组合关系以文档为准 |
| 触摸 | esp_sleep_enable_touch_wakeup()（旧名 esp_sleep_enable_touchpad_wakeup） | classic、S3 | C3 无触摸外设；唤醒脚状态查询 API 以文档为准 |
| ULP 协处理器 | 加载 ULP 程序（classic ULP-FSM；S3 ULP-FSM/RISC-V） | classic、S3 | C3 无 ULP；见官方 ULP 协处理器章 |
| UART/USB 等 | esp_sleep_enable_*_wakeup 系列子集 | 视芯片 | 仅 light sleep 有效，深睡不可用 |

## 4. 跨深睡保持数据与唤醒原因分支

```c
RTC_DATA_ATTR static uint32_t boot_count = 0;   // RTC 慢速内存：深睡保持；软复位/panic 重启也保持；上电清零
RTC_NOINIT_ATTR static uint32_t fault_mark;     // 不清零版：连上电初始化都不做
```

| esp_sleep_get_wakeup_cause() 返回 | 含义 |
|---|---|
| ESP_SLEEP_WAKEUP_TIMER | 定时到 |
| ESP_SLEEP_WAKEUP_EXT0 / ESP_SLEEP_WAKEUP_EXT1 | RTC GPIO 唤醒（classic 语义） |
| ESP_SLEEP_WAKEUP_GPIO | C3/S3 数字脚深睡唤醒 |
| ESP_SLEEP_WAKEUP_TOUCHPAD | 触摸 |
| ESP_SLEEP_WAKEUP_ULP | ULP 触发 |
| ESP_SLEEP_WAKEUP_UART | 仅 light sleep |
| ESP_SLEEP_WAKEUP_UNDEFINED | 非深睡唤醒（上电/复位） |

另有 BT/WIFI/USB/ALL 等枚举，全表以 esp_sleep.h 为准；深睡唤醒时 esp_reset_reason() 返回 ESP_RST_DEEPSLEEP。分支写法：switch(cause) 各 case 做对应采集路径，default 走冷启动初始化。

## 5. 深睡前收尾清单

| 项 | API | 不做的后果 | 取舍 |
|---|---|---|---|
| WiFi | esp_wifi_stop(); esp_wifi_deinit(); | 入睡瞬间电流尖峰、丢尾包 | 推荐做 |
| BT（用到时） | esp_bt_controller_disable()/deinit | 同上 | 按需 |
| 输出保持 | gpio_hold_en(pin)＋（S3/C3 数字脚）gpio_deep_sleep_hold_en() | 电平漂移、外设误动作（pitfall 29） | 按需 |
| RTC 域断电 | esp_sleep_pd_config(ESP_SLEEP_PD_DOMAIN_RTC_PERIPH / RTC_FAST_MEM / RTC_SLOW_MEM, ESP_SLEEP_PD_OPTION_OFF) | — | 省电到 hibernate 量级必须关；注意关 RTC_PERIPH 后 EXT0/EXT1 失效 |
| 定时器/任务 | esp_timer_stop/esp_timer_delete；在途任务收尾 | 数据未落盘 | 按需 |
| UART | uart_wait_tx_done(UART_NUM, pdMS_TO_TICKS(100)) | 最后一行日志丢失 | 推荐 |
| ADC/DAC | classic 旧 API adc_power_off()/dac_output_disable（5.x 状态以文档为准） | 漏电流 | 一般深睡自动断电，按需 |
| 其他驱动 del/deinit | i2c_master_del_bus、ledc 等 | — | 深睡=全断电，多数可不 del；light sleep 路径必须正确 del/suspend 后重 init |

## 6. 唤醒后行为与 wake stub

- 深睡唤醒=芯片复位：ROM → bootloader → app_main 从头执行；普通全局变量回初值，仅 RTC_DATA_ATTR/RTC_NOINIT_ATTR 存活。
- 判据：esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_UNDEFINED 区分深睡唤醒与冷启动；配合 RTC_DATA_ATTR 计数器统计唤醒次数。
- wake stub（进阶一句话）：esp_set_deep_sleep_wake_stub() 可在主程序之前、RTC 域仍活时先跑一段极短代码（如读个传感器再睡回去），见官方 API guide「Wake Stubs」章。
- 注意：深睡会让 S3/C3 原生 USB-Serial-JTAG 断开，monitor 掉线属正常，唤醒重启后重连。

## 7. Light sleep、Modem sleep 与 CONFIG_PM

| 项 | Light sleep | Modem sleep |
|---|---|---|
| 范围 | 整机：CPU 停、RAM 保持 | 仅 WiFi 射频按 DTIM 间歇睡 |
| CPU | 停，唤醒后原地继续 | 正常跑 |
| 唤醒源 | timer/GPIO/UART 等（esp_sleep.h） | 无（对应用透明） |
| 电流 | 数百 µA～1mA 量级（手册典型值） | 数十 mA |
| API | esp_light_sleep_start() | esp_wifi_set_ps()（STA 默认已开 MIN_MODEM） |

自动功耗管理（DFS＋自动浅睡）：

```c
esp_pm_config_t pm = { .max_freq_mhz = 240, .min_freq_mhz = 40, .light_sleep_enable = true };
esp_pm_configure(&pm);        // 需 menuconfig 启用 CONFIG_PM_ENABLE
```
副作用警示：降频使 APB 变化 → LEDC/RMT 等时序漂移（LEDC 选 LEDC_AUTO_CLK/RTC 时钟源）、esp_timer 回调延迟、任务响应抖动；实时敏感场景禁用或用 esp_pm lock 锁频。

## 8. 电池供电实操

- 稳压器静态电流常是深睡功耗主导：AMS1117 Iq 约 5mA 级，会淹没 10µA 级深睡；选 µA 级 Iq LDO（HT73xx/ME62xx 类）。
- 测量：万用表串联 µA/mA 档分段测（深睡 µA 级、活动 mA 级要换档）；要波形与平均值用功耗分析仪（PPK2/Otii 类）。
- 寿命预算：寿命(h) ≈ 电池容量(mAh)×0.8 / 平均电流(mA)；平均电流=Σ(模式电流×时间占比)，计入 WiFi 重连峰值的占空贡献。
- brownout 阈值：menuconfig → CONFIG_ESP_BROWNOUT_DET_LVL（可选档随芯片，以 menuconfig 为准）；电池内阻大时 TX 脉冲仍会触发（pitfall 1）。
- 走线与电容：电容贴近模块引脚（≥470µF＋0.1µF），电源路径短粗，避免面包板长轨。

## 9. Arduino 轨映射（arduino-esp32 3.x）

| 功能 | API（.ino 中直接可用） |
|---|---|
| 定时深睡 | esp_sleep_enable_timer_wakeup(us)＋esp_deep_sleep_start()；便捷封装 esp_deep_sleep(us)（等价 timer＋start，不返回） |
| 唤醒原因 | esp_sleep_get_wakeup_cause()（同 IDF） |
| EXT0/EXT1/GPIO 唤醒 | esp_sleep_enable_ext0_wakeup / esp_sleep_enable_ext1_wakeup / esp_deep_sleep_enable_gpio_wakeup 同名可用，芯片支持差异同 §3 |
| 输出保持 | gpio_hold_en / gpio_deep_sleep_hold_en / gpio_hold_dis |
| 浅睡 | esp_light_sleep_start() |
| 注意 | Arduino delay() 不会自动进浅睡；esp_wifi_set_ps 等 IDF API 可直接调；WiFi 前置 NVS 初始化同 pitfall 26 |
