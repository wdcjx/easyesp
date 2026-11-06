# 中断与并发纪律（ISR 铁律）

> 何时读：编写或修改任何 ISR / 中断回调 / 事件回调、或存在跨任务共享数据之前；排查偶发 `LoadProhibited` / `InstrFetchProhibited`、看门狗复位、flash 写入期间死机时。
> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

## 1. 「中断上下文」分类表

先判明回调的真实运行上下文，再套纪律等级：

| 回调 | 注册方式 | 真实上下文 | 纪律等级 |
|---|---|---|---|
| GPIO ISR | `gpio_isr_handler_add()` | 真 ISR（中断向量直调） | 铁律 A |
| timer group ISR（IDF 4.x 遗留：定义 `timer_group0_isr()` 覆盖向量） | 链接符号覆盖 | 真 ISR | 铁律 A；IDF 5.x 改用 gptimer |
| gptimer `on_alarm` 回调 | `gptimer_register_event_callbacks()` | 中断上下文；返回 `bool`，`true`=需要 yield | 铁律 A |
| UART ISR | `uart_isr_register()` | 真 ISR | 铁律 A |
| Arduino `attachInterrupt` ISR | `attachInterrupt()` | 真 ISR | 铁律 A |
| esp_timer 回调（默认 dispatch） | `esp_timer_create()` | esp_timer **任务**上下文（非 ISR），禁止阻塞 | 铁律 B |
| esp_event / WiFi 事件处理器 | `esp_event_handler_register()` / `esp_event_handler_instance_register()` | 默认事件循环任务上下文 | 铁律 B |
| ESP-NOW 收/发回调 | `esp_now_register_recv_cb()` / `esp_now_register_send_cb()` | WiFi 任务上下文 | 铁律 B |

- 铁律 A（真 ISR）：全禁阻塞；只能调 `*FromISR` API；代码 `IRAM_ATTR`；只碰内部 RAM。
- 铁律 B（任务上下文回调）：可调普通 API；禁长阻塞——此类回调阻塞会级联拖死所属服务任务（esp_timer / 事件循环 / WiFi），症状为事件延迟、TWDT、WiFi 掉线。

## 2. IRAM_ATTR 铁律

原因链：写 NVS/flash（`nvs_set_*` + `nvs_commit`、OTA、`spi_flash_*`）期间 flash cache 被禁用 → 该窗口内 CPU 只能执行位于 IRAM/ROM 的代码 → 若中断跳入 flash 中的函数（未加 `IRAM_ATTR`）→ 取指失败 → 偶发 `LoadProhibited` / `InstrFetchProhibited` panic。特征：偶发、与 flash 写时机相关。

写法（逐字）：

```c
static void IRAM_ATTR gpio_isr_handler(void *arg);
```

联动规则：
- `gpio_install_isr_service(ESP_INTR_FLAG_IRAM)`（`ESP_INTR_FLAG_IRAM` 定义于 `esp_intr_alloc.h`，经 `driver/gpio.h` 引入）：声明 ISR 服务可能在 cache 关闭期间运行；此后注册的 handler 及其调用的**所有函数**都必须 `IRAM_ATTR`。
- IDF 中 FreeRTOS `*FromISR` API 为 IRAM-safe，可在此类 ISR 内调用。
- 未加 IRAM flag 分配的中断在 flash 擦写期间被挂起（安全但延迟增大）；加了 flag 又不写 `IRAM_ATTR` = 潜在 crash。
- ISR 引用的常量表默认链接进 flash，需强制入 RAM：`static DRAM_ATTR const uint32_t s_lut[256] = { /* ... */ };`
- gptimer / UART 等驱动回调同理：配合 IRAM flag 分配时必须 `IRAM_ATTR`。

## 3. 正确 ISR 模板

### 3.1 volatile 标志位最简版（单写单读 bool）

```c
#include "driver/gpio.h"
#include "esp_attr.h"

static volatile bool s_button_pressed = false;   /* ISR 与任务共享 */

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    (void)arg;
    s_button_pressed = true;
}

static void button_init(void)
{
    const gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << GPIO_NUM_0,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    gpio_config(&io_conf);
    gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    gpio_isr_handler_add(GPIO_NUM_0, gpio_isr_handler, NULL);
}
```

### 3.2 portMUX 临界区（读-改-写 / 多字节共享）

```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE s_data_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_pulse_count = 0;
static volatile uint32_t s_last_gpio = 0;

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    portENTER_CRITICAL_ISR(&s_data_mux);        /* 中断侧专用宏 */
    s_pulse_count++;                            /* 读-改-写：非原子，必须保护 */
    s_last_gpio = (uint32_t)(uintptr_t)arg;     /* 多变量一致性：同一临界区 */
    portEXIT_CRITICAL_ISR(&s_data_mux);
}

void pulse_stats_read(uint32_t *count, uint32_t *last)
{
    portENTER_CRITICAL(&s_data_mux);            /* 任务侧配对使用 */
    *count = s_pulse_count;
    *last = s_last_gpio;
    portEXIT_CRITICAL(&s_data_mux);
}
```

### 3.3 队列传数据（含 yield）

```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"

typedef struct {
    uint32_t gpio_num;
} gpio_evt_t;

static QueueHandle_t s_evt_queue = NULL;

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    gpio_evt_t evt = { .gpio_num = (uint32_t)(uintptr_t)arg };
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xQueueSendFromISR(s_evt_queue, &evt, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken == pdTRUE) {
        portYIELD_FROM_ISR();                   /* ESP-IDF 宏，无参数 */
    }
}

static void evt_task(void *arg)
{
    gpio_evt_t evt;
    for (;;) {
        if (xQueueReceive(s_evt_queue, &evt, portMAX_DELAY) == pdTRUE) {
            /* 业务处理全在任务上下文：可打日志、可调任意 API */
        }
    }
}

static void evt_system_init(void)
{
    s_evt_queue = xQueueCreate(32, sizeof(gpio_evt_t));
    xTaskCreatePinnedToCore(evt_task, "gpio_evt", 3072, NULL, 5, NULL, 1);
    gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    gpio_isr_handler_add(GPIO_NUM_0, gpio_isr_handler, (void *)(uintptr_t)GPIO_NUM_0);
}
```

### 3.4 vTaskNotifyGiveFromISR 唤醒模式（最快路径）

```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static TaskHandle_t s_worker = NULL;

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    (void)arg;
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    vTaskNotifyGiveFromISR(s_worker, &xHigherPriorityTaskWoken);
    if (xHigherPriorityTaskWoken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static void worker_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);  /* pdTRUE=二进制语义：清零后再等 */
        /* 事件处理（任务上下文） */
    }
}
```

## 4. 共享数据保护决策表

| 场景 | 机制 | 说明 |
|---|---|---|
| ISR 置位、任务读的单标志 | `volatile bool` | 仅单写者+单读者 |
| 32 位对齐单变量的单纯读/写 | `volatile` 足够（uint32_t/指针，硬件原子） | 仍需 volatile 防编译器缓存到寄存器 |
| 计数器 `++`、读-改-写 | `portENTER_CRITICAL(_ISR)` 或 C11 `<stdatomic.h>` 的 `atomic_fetch_add`（32 位对齐时 lock-free） | RMW 序列非原子 |
| 多字节结构体 / 多变量一致性 | 同一 `portMUX_TYPE` 临界区 | 任务侧 `_CRITICAL`、中断侧 `_CRITICAL_ISR` 成对 |
| ISR→任务传事件/数据 | 队列 / 任务通知 | 不在 ISR 内做业务 |
| 任务↔任务同步 | 信号量 / 事件组 / esp_event | — |

注：`volatile` 只防编译器优化，不提供原子性；临界区内禁止任何阻塞调用，长度尽量控制在数行以内。

## 5. ISR 禁止清单（VIOLATION 级）

| 禁止项 | 原因 |
|---|---|
| `printf` / `ESP_LOGx` | 非 IRAM 且走阻塞 UART 路径；只允许置标志/发通知 |
| `malloc` / `free` / `heap_caps_malloc` | 堆操作非 ISR 安全 |
| NVS / flash 写（`nvs_set_*`、`nvs_commit`、分区写） | 慢、互斥、不可重入 |
| `vTaskDelay` / 忙等循环 | ISR 不可阻塞 |
| 任务级 FreeRTOS API（`xQueueSend`、`vTaskNotifyGive`、`xSemaphoreGive` 等） | 必须用 `*FromISR` 版本 |
| `esp_wifi_*` 绝大多数 API | WiFi 栈非 ISR 安全 |
| 浮点运算 | Xtensa（ESP32/S3）ISR 不保存 FPU 上下文，禁止；需要时用整数定点 |

## 6. DMA 与 cache（简明）

- DMA 缓冲必须位于内部 RAM：动态分配用 `heap_caps_malloc(size, MALLOC_CAP_DMA)`（该 cap 隐含内部 RAM）；或静态数组（默认链接入内部 RAM）。
- cache 一致性：常规外设（SPI/I2S 等）DMA 缓冲的一致性由驱动按官方文档处理；ESP32-S3 的 PSRAM-EDMA 路径必须满足驱动的对齐与 cache 同步要求——以对应外设驱动官方文档为准。
- PSRAM 缓冲一律不可作为普通 DMA 源/目的（S3 仅限明确支持 EDMA 的驱动路径例外）。

## 7. Arduino 轨 ISR 纪律

```cpp
#include <Arduino.h>

volatile bool s_flag = false;

void IRAM_ATTR onButton()          /* 必须 IRAM_ATTR */
{
    s_flag = true;                 /* 只置标志 */
}

void setup()
{
    pinMode(0, INPUT_PULLUP);
    attachInterrupt(0, onButton, FALLING);
}

void loop()
{
    if (s_flag) {
        s_flag = false;
        /* 打印/通信/NVS 等处理在 loopTask 上下文做 */
    }
    delay(1);
}
```

- `ICACHE_RAM_ATTR` 是旧工具链写法，已废弃，统一改 `IRAM_ATTR`。
- ISR 内同样禁 `Serial.print`、`delay`、任何分配；`attachInterrupt` 的回调等价真 ISR，铁律 A 全部适用。
