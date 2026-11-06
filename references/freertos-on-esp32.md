# ESP32 上的 FreeRTOS（与 STM32 的关键差异）

> 何时读：从 STM32 裸 FreeRTOS / CubeMX 迁移到 ESP-IDF 时；创建任务、分配栈、规划优先级、选择任务间通信原语之前。
> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

## 1. 差异总表（STM32 习惯 → ESP32 事实）

| 项 | STM32 习惯 | ESP32 事实（ESP-IDF） |
|---|---|---|
| 栈深度单位 | `xTaskCreate` 第 3 参以「字 word」计 | **字节 byte**。传 2048 即 2048 字节；按 STM32 习惯传 128 必然栈溢出 |
| 默认 tick | 常配 1000 Hz | `CONFIG_FREERTOS_HZ` 默认 **100 Hz**（1 tick=10ms，`vTaskDelay(1)` 实际约 10ms）；arduino-esp32 预编译为 1000 Hz。一律用 `pdMS_TO_TICKS()` 换算 |
| 优先级规模 | CubeMX 常配 7 级 | `configMAX_PRIORITIES`=**25**（0-24，IDF 固定，menuconfig 不可改） |
| 调度模型 | 单核抢占 | SMP 双核（ESP32/S3）：同优先级时间片轮转+跨核并行；C3 单核 |
| ISR 内任务切换 | `portEND_SWITCHING_ISR(x)` / 带参 `portYIELD_FROM_ISR(x)` | `portYIELD_FROM_ISR()`——IDF 宏**无参数** |
| 栈水位返回值 | 字 | `uxTaskGetStackHighWaterMark()` 返回**字节** |
| 看门狗 | IWDG 硬件狗 | TWDT（任务级，默认监控 IDLE）+ IWDT（中断级）两层 |
| 空闲任务 | 一般不监控 | IDLE 默认被 TWDT 监控；业务任务饿死同核 IDLE 即触发 |

## 2. 任务创建纪律

```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <assert.h>

static volatile size_t s_poll_count = 0;

static void sensor_task(void *arg)
{
    (void)arg;
    for (;;) {
        s_poll_count++;                  /* 轮询主体示例 */
        vTaskDelay(pdMS_TO_TICKS(100));  /* 周期让出：防 TWDT、让出 CPU */
    }
}

void tasks_init(void)
{
    BaseType_t ok = xTaskCreatePinnedToCore(
        sensor_task,   /* 任务入口 */
        "sensor",      /* 名字：诊断/回溯可见，小写下划线、全局唯一 */
        4096,          /* 栈：字节！含日志建议 3072-4096 */
        NULL,          /* pvParameters */
        4,             /* 优先级 0-24 */
        NULL,          /* 返回句柄，可 NULL */
        1);            /* 核亲和：0/1；C3 只能 0 或 tskNO_AFFINITY */
    assert(ok == pdPASS);
}
```

- 栈预算：最小可行 **2048 字节**起步；含 `ESP_LOGx`/`printf` 的任务建议 3072-4096（printf 族栈消耗大，经验值）。
- 复核流程：任务跑过典型负载后调 `UBaseType_t hwm = uxTaskGetStackHighWaterMark(NULL);`（历史最小剩余字节，任意时刻可查）；<256 字节即加倍栈重测。
- `xTaskCreate` vs `xTaskCreatePinnedToCore`：IDF 中前者建 tskNO_AFFINITY 任务，调度器可跨核迁移；默认一律 Pinned（行为可预期），仅辅助型低优先级任务用 `xTaskCreate`。

## 3. 核亲和策略表

| 核 | 惯例用途 | 说明 |
|---|---|---|
| core 0 | 系统/网络：WiFi/蓝牙协议栈、esp_event 默认事件循环 | 高实时业务避开 |
| core 1 | 应用与实时控制 | Arduino `loopTask` 也固定在此（C3 单核在 core 0） |
| tskNO_AFFINITY | 负载均衡型后台任务 | 调度器自由迁移；实时任务勿用 |

- `xPortGetCoreID()` 返回当前核号。
- 双核并行扩大竞态面：共享数据纪律见 isr-and-concurrency-rules.md。

## 4. 任务看门狗（TWDT）

- 监控对象：默认 core0/core1 的 IDLE 任务（`CONFIG_ESP_TASK_WDT_WATCH_IDLE_TASK_CORE0/1`，以 sdkconfig 为准）；业务任务可 `esp_task_wdt_add(handle)` 主动登记。
- 触发机理：任务在单核上长时间不让出 → 同核 IDLE 饿死 → TWDT 超时（`CONFIG_ESP_TASK_WDT_TIMEOUT_S` 默认 5 s）。
- 报文样例（样例格式）：

```
E (30034) task_wdt: task watchdog got triggered. The following tasks/users did not reset the watchdog in time:
E (30034) task_wdt:  - IDLE1 (CPU 1)
```

解读：CPU1 的 IDLE 超时——排查 CPU1 上哪个任务长跑不让出（同名任务列表即嫌疑对象）。

- 正确做法：主循环必须有让出点——`vTaskDelay()` / `vTaskDelayUntil()` / 阻塞在队列或通知上。**不是**调 `esp_task_wdt_reset()` 硬喂（那是给确实无法让出的长计算任务的最后手段，且需先登记）。
- menuconfig：`CONFIG_ESP_TASK_WDT_EN`（默认 y）、`CONFIG_ESP_TASK_WDT_TIMEOUT_S`（默认 5）、`CONFIG_ESP_TASK_WDT_PANIC`（默认 n；开启则触发即 panic）。
- IWDT 与 TWDT 一句话：IWDT 监控中断是否卡死（中断级），TWDT 监控任务/IDLE 是否饥饿（任务级）。

## 5. 通信原语选择表

| 原语 | 何时用 | ISR 版本 |
|---|---|---|
| 任务通知 `ulTaskNotifyTake` / `xTaskNotifyWait` | 唤醒单任务；最快、无队列开销；二元或计数语义 | `vTaskNotifyGiveFromISR` / `xTaskNotifyFromISR` |
| 队列 `xQueueSend` / `xQueueReceive` | ISR/任务间传小块数据（按值拷贝） | `xQueueSendFromISR` / `xQueueReceiveFromISR` |
| 事件组 `xEventGroupSetBits` | 多任务等待多事件位（位掩码） | `xEventGroupSetBitsFromISR`（内部经守护任务转交，非直通） |
| 流缓冲 `xStreamBufferSend` | 单读单写字节流 | `xStreamBufferSendFromISR` |
| 消息缓冲 `xMessageBufferSend` | 单读单写变长消息 | `xMessageBufferSendFromISR` |
| esp_event | 跨组件系统事件（WiFi/IP/自定义） | 无（任务上下文投递） |

注：流/消息缓冲限定单读者单写者（可一端为 ISR）；延迟排序：通知 < 队列 < 事件组（量级以实测为准）。

## 6. esp_timer 专节

- 微秒精度软件定时器；通用微秒时基：`int64_t esp_timer_get_time(void)`（自启动起的 µs 数，任务与 ISR 均可调用）。

```c
#include "esp_timer.h"
#include "esp_err.h"

static void on_tick(void *arg) { /* 默认在 esp_timer 任务上下文执行 */ }

void soft_timer_start(void)
{
    const esp_timer_create_args_t t_args = {
        .callback = on_tick,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,   /* 默认 */
        .name = "tick",
        .skip_unhandled_events = false,      /* 周期回调繁忙时可 true 丢弃堆积 */
    };
    esp_timer_handle_t t = NULL;
    ESP_ERROR_CHECK(esp_timer_create(&t_args, &t));
    ESP_ERROR_CHECK(esp_timer_start_periodic(t, 1000 * 1000));  /* 1 s，单位 µs */
}
```

| dispatch_method | 回调上下文 | 选择 |
|---|---|---|
| `ESP_TIMER_TASK`（默认） | esp_timer 任务（默认优先级 22，以 sdkconfig 为准） | 绝大多数场景 |
| `ESP_TIMER_ISR` | 直接中断上下文；回调须 `IRAM_ATTR` 且遵守铁律 A（需 Kconfig 启用 ISR dispatch） | 极短硬实时 |
| `ESP_TIMER_NONE` | 不自动分发，由用户调 `esp_timer_dispatch()` | 特殊自定义循环 |

- 一次性定时：`esp_timer_start_once(handle, timeout_us)`；重复 start 会报错，先 `esp_timer_stop()`。
- 设计模式：单一周期 esp_timer 回调维护「软定时器表」（到期时间戳数组），到期置标志/发通知，由工作任务统一消费——替代各任务自旋 `vTaskDelay` 轮询，节拍集中、无漂移。

## 7. 内存分配专节

| 场景 | API |
|---|---|
| 内部 RAM（可按字节写） | `heap_caps_malloc(size, MALLOC_CAP_INTERNAL \| MALLOC_CAP_8BIT)` |
| DMA 缓冲 | `heap_caps_malloc(size, MALLOC_CAP_DMA)`（必内部 RAM） |
| PSRAM 大缓冲 | `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)`；Arduino 轨 `ps_malloc()` |
| 普通小对象 | `malloc()` 默认内部 RAM；`heap_caps_malloc_extmem_enable(threshold)` 后超阈值自动转 PSRAM |

- PSRAM 禁区：DMA 源/目的、ISR 执行路径上的数据、默认任务栈（栈入 PSRAM 需 Kconfig 显式开启且受限）。
- 排查命令：

```c
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "freertos/task.h"
#include <stdio.h>

size_t free_int = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
heap_caps_print_heap_info();                                   /* heap 分区明细 */
printf("min free = %u\n", (unsigned)esp_get_minimum_free_heap_size());
UBaseType_t hwm = uxTaskGetStackHighWaterMark(NULL);           /* 当前任务最小剩余栈（字节） */
```

- WiFi 启用后典型额外堆占用约 40-60 KB（经验值，与协议/吞吐配置相关）：预估应用堆余量时先扣除。

## 8. 优先级规划建议表

| 优先级 | 用途 | 示例 |
|---|---|---|
| 0 | IDLE（TWDT 监控对象） | IDLE0 / IDLE1 |
| 1-5 | 普通应用 | 传感器轮询、UI、日志落盘；Arduino loopTask=1 |
| 6-10 | 实时控制 | 电机 PID、DMA 消费者 |
| 20 | 默认事件循环任务 | sys_evt |
| 22 | esp_timer 任务 | |
| 23 | WiFi 任务 | |

- 系统任务优先级（wifi 23、esp_timer 22 等）以 sdkconfig 为准；业务任务**不要超过**它们，否则可能饿死协议栈/定时服务。
- 同优先级任务同核时间片轮转（1 tick）；双核下同优先级可真正并行。
