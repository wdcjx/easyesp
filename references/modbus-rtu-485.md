# RS-485 与 Modbus RTU 主机从零实现（tiny485-mbrtu 转写）+ ESP32 移植

> 何时读：要在 ESP32 上接 Modbus RTU 从机（传感器、变频器、PLC、电表）——即 ESP32 作**主机**发起轮询时；或想理解 RTU 帧结构/CRC16/异常码/T3.5 时序等协议事实时；或要把一个裸机 Modbus 主机库移植到 FreeRTOS 环境时。
> 状态：实战工程沉淀（源工程 tiny485-mbrtu v1.0 / ZeroOneLab / MIT 已在 STM32F103ZE+MAX485 上板运行；本文为源码转写、未在本机二次复测；ESP32 移植代码段为按 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档新写，未经编译验证，以官方文档为准）。

## 1. 源工程定位与三层架构

tiny485-mbrtu：轻量 Modbus RTU **主机**驱动框架（ESP32 等任何带 UART 的 MCU 可移植）。核心仅 4 文件、静态内存、无第三方依赖；LUN（逻辑单元号）标识多路 485 总线，每路总线可挂 247 个从机。

```
应用层（业务轮询：采集寄存器、写控制值）
  ↕ mbrtu_build_read_holding / mbrtu_get_recv_data / mbrtu_parse_data
核心驱动层 mbrtu.c/h（帧构造、CRC16、收发缓冲、解析——平台无关，移植零改动）
  ↕ 6 个端口函数
硬件抽象层 mbrtu_port.c/h（tick、延时、串口+DE 收发切换、临界区——唯一需要改的文件）
```

| 移植面（mbrtu_port.h） | STM32 参考实现 | ESP-IDF 对应 |
|---|---|---|
| `uint32_t mbrtu_port_get_tick(void)` | `HAL_GetTick()` | `esp_timer_get_time()/1000`（或 `xTaskGetTickCount()*portTICK_PERIOD_MS`） |
| `void mbrtu_port_delay_ms(uint32_t)` | `HAL_Delay(ms)` | `vTaskDelay(pdMS_TO_TICKS(ms))`（注：核心层实际未调用它，属可选端口） |
| `void mbrtu_port_init(uint8_t lun)` | `HAL_UART_Receive_IT(...,1)` + DE 拉低 | UART 驱动安装 + 事件队列任务（见 §4） |
| `void mbrtu_port_send(uint8_t lun, uint8_t*, uint16_t)` | DE 拉高→延时 1ms→阻塞发送→DE 拉低 | DE 拉高→`uart_write_bytes`→**`uart_wait_tx_done`**→DE 拉低（或硬件 RS485 模式免手动） |
| `mbrtu_port_enter/exit_critical(lun)` | 裸机留空 | `portENTER_CRITICAL(&lock)` / mutex（多任务必须真实现） |

多路总线：`MBRTU_NUM` 定总线路数；`MBRTU_LUN_USER1/2` 是 switch-case 的索引；每 LUN 独立 64B 静态接收缓冲。注意 LUN 无越界检查（见坑 #119）。

## 2. Modbus RTU 协议事实速查（主机视角）

| 事实 | 值/规则 |
|---|---|
| 帧结构 | `[从机地址1B][功能码1B][数据nB][CRC低][CRC高]`，无起始/结束符，靠总线静默分帧 |
| CRC16 | 多项式 0xA001（0x8005 反转），初值 0xFFFF，无最终异或；**发送时低字节在前**（小端序是 CRC 自己的，数据字段全大端） |
| 从机地址 | 1–247 有效；0=广播（写广播不回响应）；248–255 保留 |
| 常用功能码 | 0x01 读线圈 / 0x02 读离散输入 / 0x03 读保持寄存器 / 0x04 读输入寄存器 / 0x05 写单线圈 / 0x06 写单寄存器 / 0x0F 写多线圈 / 0x10 写多寄存器 |
| 数量上限（规范） | 0x03/0x04 ≤125 寄存器；0x01/0x02 ≤2000 位；0x10 ≤123 寄存器（tiny485 README 写"读≤123"系笔误级误导，见坑 #117/#118） |
| 异常响应 | 功能码最高位置 1（fc\|0x80）+ 1B 异常码：01 非法功能 / 02 非法地址 / 03 非法数据 / 04 从机故障 / 06 忙 |
| 串口参数 | 规范默认 **8E1**（偶校验）；无校验时规范要求 8N2；实践中 **8N1 最普遍**（绝大多数设备出厂默认），跨设备对接先对齐参数 |
| 帧间隔 | 帧间静默 ≥T3.5（3.5 字符时间）；字符间 >T1.5 判帧断。>19200 波特率固定 T1.5=750µs、T3.5=1.75ms；9600 下 T3.5≈3.65ms |
| 字节耗时 | 8N1=10 bit/字节：9600 下 ≈1.042ms/字节；8B 请求帧 ≈8.3ms，读 2 寄存器响应 9B ≈9.4ms |
| 读保持寄存器示例 | 请求 `01 03 00 00 00 02 C4 0B`；响应 `01 03 04 D1 D2 D3 D4 crc_lo crc_hi`（04=字节数）；异常 `01 83 02 crc` |

## 3. 核心层精读（mbrtu.c，256 行全读）

**CRC16 位算法**（无表、省内存首选；查表法 256×2B 换速度）：

```c
static uint16_t mbrtu_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;              /* 初值 */
    while (len--) {
        crc ^= *data++;
        for (uint8_t i = 0; i < 8; i++)
            crc = (crc & 0x0001) ? (crc >> 1) ^ 0xA001 : (crc >> 1);
    }
    return crc;                          /* 追加时低字节在前 */
}
```

**请求构造**（0x03 与 0x06 同构，均为定长 8B）：地址/功能码/起始地址大端/数量大端/CRC 低在前。发送序列固定为：进临界区→**清接收缓冲**→发送→出临界区。清缓冲在发送前，防止上一轮残留被当成响应。

**接收路径**：`mbrtu_recv_handler(lun, data, len)` 由串口收数回调喂入——先判 `(cnt+len) >= BUF_SIZE` 溢出（**丢弃整包**：cnt 清零，返回 1），否则追加并刷新接收时间戳。`volatile` 修饰 cnt/tick 数组（ISR 与主循环共享），正确。

**等待与解析**：`mbrtu_wait_data` 忙等固定 timeout 后只查一次 `recv_cnt`（设计缺陷见坑 #116/#117）；`mbrtu_parse_data` 校验最短 5B→CRC（`crcRx = (raw[len-1]<<8)|raw[len-2]` 与低在前匹配）→异常帧判 `fc & 0x80`（返回 ERR_EXCEPTION 且 PDU=地址+功能码+异常码 3B）→正常帧去掉 2B CRC 整体拷出。`mbrtu_get_recv_data` 返回**静态缓冲区指针**并复位计数（单事务流程安全，多任务并发有竞态）。

**超时回绕安全**：`now - start < timeout` 用无符号减法，uint32_t tick 自然回绕安全——标准写法，值得照抄。

## 4. ESP32 移植——ESP-IDF 轨

### 4.1 方案 A：硬件 RS485 模式（推荐，零手动方向控制）

ESP32 UART 外设原生支持 RS485 半双工：RTS 脚接收发器 DE/RE，硬件在发送期间自动拉高、发完自动回落——省掉手动 DE、切换延时、以及"发送完成前拉低截尾"整类坑（#120/#124）。

```c
#include "driver/uart.h"

#define MB_UART      UART_NUM_1
#define MB_BAUD      9600
#define MB_RX_PIN    18      /* 接 MAX485 RO */
#define MB_TX_PIN    17      /* 接 MAX485 DI */
#define MB_DE_PIN    8       /* 接 MAX485 DE+/RE-，用 UART 硬件 RTS 驱动 */

static QueueHandle_t mb_uart_queue;

void mb_port_init(void)
{
    uart_config_t cfg = {
        .baud_rate = MB_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_param_config(MB_UART, &cfg);
    uart_set_pin(MB_UART, MB_TX_PIN, MB_RX_PIN, MB_DE_PIN, UART_PIN_NO_CHANGE);
    uart_driver_install(MB_UART, 256, 256, 20, &mb_uart_queue, 0);
    uart_set_mode(MB_UART, UART_MODE_RS485_HALF_DUPLEX);  /* RTS 自动方向 */
}

/* 发送端口函数：无手动 DE，直接写 */
void mbrtu_port_send(uint8_t lun, uint8_t *buf, uint16_t len)
{
    uart_write_bytes(MB_UART, (const char*)buf, len);
    uart_wait_tx_done(MB_UART, pdMS_TO_TICKS(100));      /* 等硬件发完（含 RS485 回落） */
}
```

注意：RS485 半双工模式下接收器仍使能，部分接法会收到自身发送的回显（以官方文档与实测为准）；若用 `UART_MODE_RS485_HALF_DUPLEX` 且接线为 DE 与 /RE 绑一起，发送期接收器关闭、无回显。

### 4.2 方案 B：手动 GPIO 方向控制

普通 UART + 任一 GPIO 当 DE，方向纪律全在软件（纪律错误即 #120）：

```c
static void mb_send_bytes(const uint8_t *buf, uint16_t len)
{
    gpio_set_level(MB_DE_GPIO, 1);                       /* 进发送态 */
    ets_delay_us(10);                                    /* 收发器建立时间（µs 级即可，勿 ms） */
    uart_write_bytes(MB_UART, (const char*)buf, len);    /* 仅入队！ */
    uart_wait_tx_done(MB_UART, pdMS_TO_TICKS(100));      /* 必须：等真实发完 */
    gpio_set_level(MB_DE_GPIO, 0);                       /* 之后才准回接收态 */
}
```

铁律：`uart_write_bytes` 返回≠字节上总线（写入 TX FIFO/环形缓冲即返回）；`uart_wait_tx_done`（或 `uart_tx_wait_idle`）之后才能动 DE。源工程 STM32 端 `HAL_UART_Transmit` 是阻塞语义所以紧跟拉低没错，移植到 IDF 时**必须补 wait_tx_done**。

### 4.3 接收喂入：事件队列任务（替代 STM32 的逐字节中断回调）

STM32 示例在 `HAL_UART_RxCpltCallback`（中断上下文）里调 `mbrtu_recv_handler` 并重挂接收。ESP-IDF 正确姿势是事件任务（任务上下文调核心层，天然满足 ISR 瘦身纪律）：

```c
static void mb_uart_task(void *arg)
{
    uart_event_t ev;
    uint8_t tmp[64];
    for (;;) {
        if (xQueueReceive(mb_uart_queue, &ev, portMAX_DELAY)) {
            if (ev.type == UART_DATA) {
                int n = uart_read_bytes(MB_UART, tmp, ev.size, pdMS_TO_TICKS(20));
                if (n > 0) mbrtu_recv_handler(MBRTU_LUN_USER1, (const uint8_t*)tmp, (uint16_t)n);
            } else if (ev.type == UART_FIFO_OVF || ev.type == UART_BUFFER_FULL) {
                uart_flush_input(MB_UART);               /* 防死锁 */
                xQueueReset(mb_uart_queue);
            }
        }
    }
}
```

### 4.4 其余端口

- `get_tick`：`(uint32_t)(esp_timer_get_time() / 1000)`——µs 精度足够 T3.5 级判断。
- 临界区：单任务轮询可留空；多任务共享同一 LUN 必须实现（`portMUX_TYPE` 自旋锁或 mutex；临界区只包"清缓冲+发送"，勿把等待循环也包进去）。
- **等待循环改造（必做）**：原 `mbrtu_wait_data` 忙等烧满超时且无 yield，在 FreeRTOS 上会饿死同核低优先级任务、可触发任务看门狗。改为轮询+让出：

```c
static uint8_t mbrtu_wait_data_fixed(uint8_t lun, uint32_t timeout)
{
    uint32_t start = mbrtu_port_get_tick();
    uint16_t last = 0;
    while (mbrtu_port_get_tick() - start < timeout) {
        if (mbrtu_recv_cnt[lun] > last) {                /* 有新字节 */
            last = mbrtu_recv_cnt[lun];
            start = mbrtu_port_get_tick();               /* 重置：按帧间隔判结束 */
        }
        vTaskDelay(pdMS_TO_TICKS(2));                    /* 让出 CPU */
    }
    return (mbrtu_recv_cnt[lun] == 0) ? MBRTU_ERR_TIMEOUT : MBRTU_OK;
}
```

顺带把"烧满固定超时"升级为"字节间隔判帧完"（idle≥2ms 视为帧完，仍保守于 T3.5=3.65ms@9600），响应到达即返回，轮询吞吐量数量级提升。

### 4.5 调用骨架

```c
/* 单一"Modbus 轮询任务"内串行调用，勿在 app_main/loop 直接长阻塞 */
uint8_t st = mbrtu_build_read_holding(LUN, 0x01, 0x0000, 2, 100);
if (st == MBRTU_OK) {
    uint8_t *raw; uint16_t rlen; uint8_t pdu[64], plen;
    if (mbrtu_get_recv_data(LUN, &raw, &rlen) == MBRTU_OK
        && mbrtu_parse_data(LUN, raw, rlen, pdu, &plen) == MBRTU_OK) {
        /* pdu[0]=地址 pdu[1]=0x03 pdu[2]=字节数 pdu[3..]=寄存器值大端 */
    }
}
```

## 5. ESP32 移植——Arduino 轨

```cpp
#include <HardwareSerial.h>
#define DE_PIN 4
HardwareSerial MB(2);            /* UART2 */

void setup() {
    MB.begin(9600, SERIAL_8N1, /*rx*/18, /*tx*/17);
    pinMode(DE_PIN, OUTPUT);
    digitalWrite(DE_PIN, LOW);   /* 默认接收态 */
}

void mbRequest(const uint8_t *req, size_t n) {
    digitalWrite(DE_PIN, HIGH);
    delayMicroseconds(10);
    MB.write(req, n);
    MB.flush();                  /* arduino-esp32: 等 TX 完成（≠AVR 清 RX 语义） */
    digitalWrite(DE_PIN, LOW);
}
```

要点：arduino-esp32 的 `flush()` 语义是等待发送完成（与旧 AVR 的"丢弃接收"不同），正好当 `uart_wait_tx_done` 用；收数侧轮询 `MB.available()/MB.readBytes()` 追加进 `mbrtu_recv_handler`。

## 6. 与 env-controller（MicroPython 商用主机）的取舍

| 维度 | tiny485-mbrtu（本文） | env-controller sensor 服务（[micropython-env-controller.md](micropython-env-controller.md) §3） |
|---|---|---|
| 语言/运行时 | 纯 C、裸机或 RTOS 均可 | MicroPython asyncio |
| 主机模型 | 阻塞轮询（单事务一发一收） | 配置驱动指令-通道 schema、周期调度、失败继承旧值 |
| 帧结束判定 | 固定超时（改造版：字节间隔） | 帧空闲 30ms + CRC + 补读 |
| 方向控制 | 软件或 UART RS485 硬件模式 | C 下沉 de_write 硬件判定 |
| 适用 | 单任务专注采集、小内存、C 工程集成、学习协议 | 多设备多协议商用网关、热配置 |

选型：ESP-IDF/Arduino 工程里做 RTU 主机直接用本文 §4/§5；需要多总线多设备调度、失败兜底策略时参考 env-controller 的 schema 层设计叠在上面。

## 7. 纪律对照（validator 视角）

- `mbrtu_recv_handler` 在 STM32 是中断上下文调用；ESP-IDF 上已改任务上下文（§4.3）——ISR 瘦身纪律的正面示范。
- cnt/tick 用 `volatile` 正确；但仍存在非原子读竞态（16 位 cnt 在 32 位机上原子，侥幸安全；get_recv_data 的"返回指针+复位"与中断并发是真实竞态，靠单事务流程回避）。
- 临界区方向正确：包"清缓冲+发送"（防中断把旧数据当响应），不包等待循环（临界区最小化）。

## 8. 可复用模式

1. 三层移植面：协议核心零改动，6 个端口函数换平台——同样适用于 CoAP/私有协议栈。
2. LUN 分路：索引而非对象多态，C 里多路总线最省的抽象。
3. 无符号 tick 差值判超时：`now - start < timeout` 天然回绕安全。
4. CRC16 位算法无表实现：小内存首选；吞吐敏感再换查表。
5. 请求前清缓冲 + 临界区包发送：多任务共享总线的主机必备。
6. "字节间隔判帧完"替代定长超时：响应到达即返回，轮询频率不再被超时值锁死。
7. ESP32 硬件 RS485 模式：能免的手动 DE 一律免——方向控制交给硬件是唯一不会错的时序。

## 9. 坑位索引

本文相关坑位见 [known-pitfalls.md](known-pitfalls.md) **#116–124**：等待循环忙等烧满超时（RTOS 饿死）、响应超长溢出伪装 TIMEOUT、ERR_PARAM 从不返回、LUN 越界、DE 拉低截尾（IDF 写函数仅入队）、溢出后半帧当新帧、广播写误报超时、DE/RE 接法决定回显有无、DE 建立延时写死 1ms 降吞吐。
