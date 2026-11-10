# 按键输入状态机（MultiButton 模式）

> 何时读：需求含「单击 / 双击 / 长按 / 连击」任一词汇，或 GPIO 按键需要事件分类而非裸电平时。外设原始输入与简单防抖见 `peripheral-recipes.md`，本文是它之上的事件层。
> 状态：库研读（MultiButton v1.1.1 源码逐行精读，未上板实测；API 对齐本仓库源码；MIT 许可可直接 vendor）。

## 1. 库定位与事实

MultiButton（原作者 Zibin Zheng，2016/2018，MIT）是嵌入式 C 事实标准的多按键状态机库；本文基于其现代化 fork v1.1.1（2026-03，在原版上补齐 `user_data` 上下文、可选线程安全、单元测试、CMake/CI；修了 REPEAT→PRESS 转移不清零导致误判长按的 bug）。

| 事实 | 值 |
|---|---|
| 构成 | `multi_button.c`(321 行) + `multi_button.h`(116 行)，零依赖（仅 stdint/string.h） |
| 许可 | MIT（2018 Zibin Zheng）——可直接拷入工程，保留版权头即可 |
| 内存 | 每键一个 `Button` 结构体（约 24B，无动态分配）+ 单向链表 |
| 节拍模型 | 外部每 5ms 调一次 `button_ticks()`（定时器或任务），库内无时间源 |
| 双轨可用性 | ESP-IDF / Arduino 通用（纯 C，HAL 只要求一个读电平函数指针） |

## 2. 数据模型（位域打包）

`struct _Button` 用位域把状态压进字节：`repeat:4`（连击计数 0–15）、`event:4`（当前事件，8 种 + NONE 恰好 4 bit）、`state:3`（5 个状态）、`debounce_cnt:3`（防抖计数 **上限 7，编译期 `#error` 强制**）、`active_level:1`、`button_level:1`。

时序参数全部以「tick 数」表达（宏在 multi_button.h 顶部）：

| 宏 | 默认 | 换算 | 含义 |
|---|---|---|---|
| `TICKS_INTERVAL` | 5 | 5ms | 节拍周期，调用方必须按此间隔喂 `button_ticks()` |
| `DEBOUNCE_TICKS` | 3 | 15ms | 新电平须连续出现 3 拍才被采信 |
| `SHORT_TICKS` | 60 | 300ms | 释放后等待第二击的窗口；超过即判定单击/双击 |
| `LONG_TICKS` | 200 | 1000ms | 按住超过即长按开始 |
| `PRESS_REPEAT_MAX_NUM` | 15 | — | 连击计数上限（4-bit 饱和，到顶不再加） |

⚠ 参数耦合：SHORT/LONG 都由 `毫秒 / TICKS_INTERVAL` 算出——改 `TICKS_INTERVAL` 会联动全部阈值，这是设计也是坑（节拍抖动直接变成时序误差）。

## 3. 状态机精读（5 状态 8 事件）

```
IDLE ──按下──> PRESS ──释放──> RELEASE ──300ms 超时──> IDLE（发 SINGLE/DOUBLE_CLICK）
                 │              │ 再按下
                 │1000ms         ▼
                 ▼            REPEAT ──快速释放──> RELEASE（继续等更多击）
             LONG_HOLD <─按住── └─按住超 300ms──> PRESS（ticks/repeat 清零重来）
```

- **IDLE→PRESS**：防抖后的首个按下沿，发 `PRESS_DOWN`，`ticks=0, repeat=1`。
- **PRESS**：释放→发 `PRESS_UP` 进 RELEASE；按住超 `LONG_TICKS`→发 `LONG_PRESS_START` 进 LONG_HOLD。
- **RELEASE**（事件分类核心）：窗口内再按下→`repeat++` 并发 `PRESS_REPEAT` 进 REPEAT；窗口超时→`repeat==1` 发 `SINGLE_CLICK`、`repeat==2` 发 `DOUBLE_CLICK`、**`repeat>2` 无枚举事件**（三击以上只能靠 `PRESS_REPEAT` 回调里读 `button_get_repeat_count()`），回 IDLE。
- **REPEAT**：快速释放（<SHORT_TICKS）→回 RELEASE 继续累计；按住超窗→回 PRESS 且 `ticks=0, repeat=0`（v1.1.0 修复点：旧版此处不清零，连击第二下按久一点会被误判立即长按）。
- **LONG_HOLD**：每个 tick 都发 `LONG_PRESS_HOLD`（**5ms 一次**）；释放发 `PRESS_UP` 回 IDLE。
- `ticks` 仅在非 IDLE 态自增且在 `UINT16_MAX` 饱和（防回绕）。

## 4. API 与两种用法

```c
// 回调模式（推荐）
button_init(&btn, read_gpio_fn, active_level, button_id);      // memset 清零+挂 HAL
button_attach(&btn, BTN_SINGLE_CLICK, on_click, user_data);    // 每事件一个槽
button_start(&btn);                                            // 挂入链表（重复挂返回 -1）
// 每 5ms：button_ticks();   —— 回调在 button_ticks 调用线程同步执行

// 轮询模式（不打回调，主循环查）
button_attach 全不挂；ButtonEvent ev = button_get_event(&btn); // 读最近事件
```

API 面：`button_detach/reset/stop`、`button_get_repeat_count`、`button_is_pressed`。注意 `user_data` 是**每键共享一个**（不是每事件一个）——一个键要多种上下文得自己打包结构体。线程安全默认关闭；RTOS 下定义 `MULTIBUTTON_THREAD_SAFE` + `MULTIBUTTON_LOCK/UNLOCK` 宏（例：FreeRTOS `xSemaphoreTake`），回调在锁外执行故可用非递归锁、回调内可安全 `button_stop()`。

## 5. ESP-IDF 集成配方（可直接抄）

```c
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "multi_button.h"

#define BTN_GPIO  GPIO_NUM_0          // BOOT 键，低电平有效（板载上拉）
static Button btn_boot;

static uint8_t btn_gpio_read(uint8_t id) {
    (void)id;
    return (uint8_t)gpio_get_level(BTN_GPIO);   // HAL 只需这一个函数
}

void app_main(void) {
    gpio_config_t io = { .pin_bit_mask = 1ULL << BTN_GPIO,
                         .mode = GPIO_MODE_INPUT,
                         .pull_up_en = GPIO_PULLUP_ENABLE };
    gpio_config(&io);

    button_init(&btn_boot, btn_gpio_read, 0, 1);          // active_level=0
    button_attach(&btn_boot, BTN_SINGLE_CLICK,   on_single, NULL);
    button_attach(&btn_boot, BTN_DOUBLE_CLICK,   on_double, NULL);
    button_attach(&btn_boot, BTN_LONG_PRESS_START, on_long,  NULL);
    button_start(&btn_boot);

    while (1) {                    // 任务节拍（推荐）：回调即在本任务上下文
        button_ticks();
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
```

要点：①节拍放 **FreeRTOS 任务**而非 gptimer ISR——`button_ticks` 会在调用上下文同步执行全部回调，放 ISR 则回调全进中断上下文（铁律禁止）；若坚持定时器，只置标志、任务里清标志后调 `button_ticks`。②`active_level` 必须与外部电路一致：上拉+按键接地=0；下拉/按键接 VCC=1。③MANIFEST 里声明 `gpio0 button`，M 系列核对。④vendor 方式：`components/multibutton/{multi_button.c,multi_button.h,CMakeLists.txt}`（`idf_component_register(SRCS "multi_button.c" INCLUDE_DIRS ".")`）。

## 6. Arduino 轨集成

```cpp
#include <Arduino.h>
#include "multi_button.h"
static Button btn;
static uint8_t btn_read(uint8_t id) { (void)id; return digitalRead(BOOT_BTN_PIN); }

void setup() {
    pinMode(BOOT_BTN_PIN, INPUT_PULLUP);
    button_init(&btn, btn_read, 0, 1);
    button_attach(&btn, BTN_SINGLE_CLICK, on_single, NULL);
    button_start(&btn);
}
void loop() {
    button_ticks();                 // loop 快于 5ms 时可每 5 次调 1 次
    delay(5);
}
```

Arduino 生态另有 OneButton 库（同类思想、面向对象）；生成时两者取一，MultiButton 优势是纯 C、IDF/Arduino 同一份代码。

## 7. 何时 vendor / 何时自写精简

| 场景 | 建议 |
|---|---|
| 需要单击+双击+长按任意组合，多按键 | vendor MultiButton（MIT，2 文件，时序已被测试覆盖） |
| 只要单击（无长按/双击） | 不必引库：`peripheral-recipes.md` 的沿检测+防抖 10 行足够 |
| 需要三击/四击 | vendor + `PRESS_REPEAT` 回调里读 `button_get_repeat_count()` 自行分档 |
| 深度定制（组合键、按键队列） | 抄本库状态机骨架自写（§3 转移表即全部逻辑） |

## 8. 注意事项（库特性类，不入实战坑清单）

- **单击事件有固有 ≥300ms 延迟**：RELEASE 态必须等满 `SHORT_TICKS` 窗口确认没有第二击才发 `SINGLE_CLICK`。对响应敏感的 UI 可调小 `SHORT_TICKS`（如 200ms），代价是双击窗变紧。
- **`LONG_PRESS_HOLD` 以 5ms 频率连续触发**：回调里禁止 printf/重活/阻塞（会拖垮节拍任务）；做「长按步进调值」时用它天然节流，但别再自加 delay。
- `button_ticks()` 节拍抖动=时序误差：任务优先级别太低（Wi-Fi/BT 忙时 5ms 任务被饿，长按阈值实际漂移）；对精度敏感可升优先级或用高分辨率定时器置标志。
- 按键电平读取函数在 `button_ticks` 上下文执行，只许 `gpio_get_level`/`digitalRead` 级别操作。
- 多任务同时 `button_start/stop`（如热插拔配置键）才需要线程安全宏；常规「init 后只读」无需。

## 9. 与本技能其它文档的关系

`peripheral-recipes.md`（GPIO 输入+防抖）→ 本文（事件分类层）→ `isr-and-concurrency-rules.md`（节拍任务优先级与回调上下文纪律）→ `known-pitfalls.md`（#94–101 有 Mind+ 按键扫描类坑可对照）。
