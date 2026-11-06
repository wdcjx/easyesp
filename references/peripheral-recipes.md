# 外设配方速查（ESP-IDF）

> 何时读：要在 esp32/esp32s3/esp32c3 上初始化外设抄代码时，按小节直达。
> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

通用：`ESP_ERROR_CHECK()` 出错即 abort；引脚为经典 esp32 例；各节末行 Arduino 对应，细节见 `arduino-track.md`。

## 1. GPIO 输出 / 输入按键（含去抖）

```
#include "driver/gpio.h"
#include "esp_timer.h"
#define LED_GPIO GPIO_NUM_2
#define BTN_GPIO GPIO_NUM_0  // Boot 键低有效
void led_init(void) {
    // 写法 A：gpio_config 批量配置（其余字段零值即可）
    gpio_config_t io = { .pin_bit_mask = 1ULL << LED_GPIO, .mode = GPIO_MODE_OUTPUT };
    gpio_config(&io);
    // 写法 B：reset 清残留，可重复 init
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GPIO, 0);
}
static bool btn_st, btn_last; static int64_t btn_t;
bool btn_falling_edge(void) {  // 10ms 调；true=按下（20ms 去抖）
    bool raw = gpio_get_level(BTN_GPIO) == 0;
    if (raw != btn_last) { btn_last = raw; btn_t = esp_timer_get_time(); }
    if (raw != btn_st && esp_timer_get_time() - btn_t > 20000) { btn_st = raw; return btn_st; }
    return false;
}
```

坑：esp32 GPIO34–39 仅输入无上下拉；复用被占引脚先 `gpio_reset_pin()`；中断需 `gpio_install_isr_service()`+`gpio_isr_handler_add()`。Arduino：`pinMode/digitalWrite/digitalRead`。

## 2. 微秒时基 + 非阻塞主循环（millis() 模式正解）

```
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
typedef struct { int64_t last_us, period_us; void (*fn)(void); } soft_timer_t;
static soft_timer_t s_timers[] = { { .period_us = 10000, .fn = btn_tick } };  // 按需增条目
void app_main(void) {
    for (;;) {
        int64_t now = esp_timer_get_time();  // 自开机微秒，不回绕
        for (size_t i = 0; i < sizeof(s_timers) / sizeof(s_timers[0]); i++)
            if (now - s_timers[i].last_us >= s_timers[i].period_us) {
                s_timers[i].last_us = now; s_timers[i].fn();
            }
        vTaskDelay(pdMS_TO_TICKS(10));  // 让出 CPU
    }
}
```

坑：勿截 32 位比较；1ms 精度需 CONFIG_FREERTOS_HZ=1000（默认 100）；`app_main` `return` 即自删，须 `for(;;)`。Arduino：内置 `millis()/micros()`。

## 3. UART 控制台与 UART1

UART0=默认控制台（esp32 GPIO1/3；s3/c3 常为 USB-JTAG）：直接 `ESP_LOGI()/printf()`。

```
#include "driver/uart.h"
#define U1 UART_NUM_1
void uart1_init(void) {
    uart_config_t cfg = { .baud_rate = 115200, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT };
    uart_param_config(U1, &cfg);
    uart_set_pin(U1, 17, 18, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);  // TX=17 RX=18
    uart_driver_install(U1, 2048, 0, 0, NULL, 0);  // rx 缓冲 2KB
}
int uart1_tx(const uint8_t *d, size_t n) { return uart_write_bytes(U1, (const char *)d, n); }
int uart1_rx(uint8_t *buf, size_t n, int ms) {  // 返回实收数，超时 0
    return uart_read_bytes(U1, buf, n, pdMS_TO_TICKS(ms));  // 第 4 参 TickType_t
}
```

坑：读前须装 driver；不定长帧先 `uart_get_buffered_data_len(U1,&len)` 再读；另有 `uart_read_bytes_timeout_ms`，以官方文档为准。Arduino：`Serial1.begin(115200,SERIAL_8N1,RX,TX)`，RX 在前。

## 4. I2C master（5.2+ 新驱动）

```
#include "driver/i2c_master.h"
static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_dev;
void i2c_init(void) {
    i2c_master_bus_config_t bus = {
        .sda_io_num = GPIO_NUM_21, .scl_io_num = GPIO_NUM_22,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,  // 有外部上拉置 false
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus, &s_bus));
    i2c_device_config_t dev = { .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = 0x48, .scl_speed_hz = 100000 };  // 7 位地址；400k 多数支持
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_bus, &dev, &s_dev));
}
esp_err_t reg_read(uint8_t reg, uint8_t *buf, size_t n) {  // 写 reg 后读 N 字节
    return i2c_master_transmit_receive(s_dev, &reg, 1, buf, n, 100);  // 末参 xfer_timeout_ms
}
esp_err_t reg_write(uint8_t reg, uint8_t v) {
    uint8_t b[2] = { reg, v };
    return i2c_master_transmit(s_dev, b, 2, 100);
}
```

坑：旧 `driver/i2c.h` deprecated 仅迁移用；新 API 自带 timeout 不卡总线；多从机多次 add_device；探测 `i2c_master_probe(s_bus,addr,100)`；无 ACK 返 ESP_ERR_TIMEOUT。Arduino：`Wire.begin(SDA,SCL)`+`Wire.requestFrom()`。

## 5. SPI master

```
#include "driver/spi_master.h"
static spi_device_handle_t s_spi;
void spi_init(void) {
    spi_bus_config_t bus = { .mosi_io_num = 23, .miso_io_num = 19, .sclk_io_num = 18,
        .quadwp_io_num = -1, .quadhd_io_num = -1 };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
    spi_device_interface_config_t dev = { .mode = 0, .clock_speed_hz = 1000000,
        .spics_io_num = 5, .queue_size = 7 };  // 上限看从机，典型≤40MHz
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &s_spi));
}
esp_err_t spi_rw(uint8_t *tx, uint8_t *rx, size_t n) {  // 全双工
    spi_transaction_t t = { .length = n * 8, .tx_buffer = tx, .rx_buffer = rx };
    return spi_device_transmit(s_spi, &t);
}
```

坑：DMA 下 tx/rx 缓冲须内部 RAM：`heap_caps_malloc(n,MALLOC_CAP_DMA)`，PSRAM 指针报错；`length` 单位 bit；c3 仅 SPI2_HOST。Arduino：`SPI.begin(sck,miso,mosi,cs)`+`SPI.beginTransaction()`。

## 6. LEDC PWM

```
#include "driver/ledc.h"
void pwm_1khz_init(void) {  // 呼吸灯 1kHz/10bit
    ledc_timer_config_t tim = {
        .speed_mode = LEDC_LOW_SPEED_MODE,  // LEDC_HIGH_SPEED_MODE 仅经典 esp32
        .timer_num = LEDC_TIMER_0, .duty_resolution = LEDC_TIMER_10_BIT,
        .freq_hz = 1000, .clk_cfg = LEDC_AUTO_CLK };
    ESP_ERROR_CHECK(ledc_timer_config(&tim));
    ledc_channel_config_t ch = { .gpio_num = GPIO_NUM_2, .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0, .timer_sel = LEDC_TIMER_0 };  // 其余零值
    ESP_ERROR_CHECK(ledc_channel_config(&ch));
}
void pwm_set(uint32_t duty) {  // 0 ~ 2^duty_resolution-1
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);  // 不 update 不生效
}
```

舵机 50Hz：freq_hz=50、LEDC_TIMER_14_BIT：1.0ms≈819、1.5ms≈1229、2.0ms≈1638；SG90 类 1.0–2.0ms 对应 ±90°（数据手册典型值）。

坑：硬约束 `freq_hz × 2^duty_resolution ≤ 源时钟`（典型 80MHz）：20kHz×2^12≈81.9MHz 失败，降位深或降频；改频重跑 `ledc_timer_config`。Arduino（3.x）：`ledcAttach(pin,freq,res)`+`ledcWrite(pin,duty)`；2.x ledcSetup 已改。

## 7. ADC oneshot + 校准 + 均值滤波

```
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;
#define ADC_CH ADC_CHANNEL_4  // esp32=GPIO32；s3=GPIO5；c3=GPIO4
void adc_init(void) {
    adc_oneshot_unit_init_cfg_t init = { .unit_id = ADC_UNIT_1, .ulp_mode = ADC_ULP_MODE_DISABLE };
    ESP_ERROR_CHECK(adc_oneshot_new_adc_unit(&init, &s_adc));
    adc_oneshot_chan_cfg_t ch = { .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, ADC_CH, &ch));
    adc_cali_line_fitting_config_t cali = { .unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_12 };
    if (adc_cali_create_scheme_line_fitting(&cali, &s_cali) != ESP_OK) s_cali = NULL;  // eFuse 无数据
}
int adc_read_mv_avg(int n) {  // 均值滤波；-1=读失败
    int raw = 0, mv = 0; long sum = 0;
    for (int i = 0; i < n; i++) {
        if (adc_oneshot_read(s_adc, ADC_CH, &raw) != ESP_OK) return -1;
        if (adc_cali_raw_to_voltage(s_cali, raw, &mv) != ESP_OK) mv = raw * 3100 / 4095;  // 粗算
        sum += mv;
    }
    return (int)(sum / n);
}
```

坑：ADC2 与 Wi-Fi 冲突铁律（Wi-Fi 运行时采样失败），共存模拟量一律接 ADC1；ATTEN_DB_12 典型量程 0–2.4V（esp32）/0–3.1V（s3/c3），近满量程非线性明显（数据手册典型值）。Arduino：`analogReadMilliVolts()`。

## 8. WS2812（led_strip 组件）

依赖：`main/idf_component.yml` 加 `espressif/led_strip: ^2.5.0`

```
#include "led_strip.h"
static led_strip_handle_t s_ws;
void ws2812_init(void) {
    led_strip_config_t strip = { .strip_gpio_num = GPIO_NUM_8, .max_leds = 1,
        .led_model = LED_MODEL_WS2812,
        .color_component_format = LED_STRIP_COLOR_COMPONENT_FORMAT_GRB };  // 其余零值
    led_strip_rmt_config_t rmt = { .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10000000, .flags.with_dma = false };  // mem_block_symbols 默认 64
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip, &rmt, &s_ws));
    led_strip_clear(s_ws);
}
void ws2812_set(uint8_t r, uint8_t g, uint8_t b) {
    led_strip_set_pixel(s_ws, 0, r, g, b);  // 只写缓冲
    ESP_ERROR_CHECK(led_strip_refresh(s_ws));  // refresh 才发波形
}
```

坑：RMT 硬件时序，勿位 banging；结构体字段随 led_strip 版本（2.x/3.x）有异，以组件官方文档为准；WS2812 阈值 0.7×VDD，5V 供电 3.3V 直驱临界（经验值），加电平转换稳妥；多灯串联 max_leds=链长。Arduino：`neopixelWrite(pin,r,g,b)` 或 Adafruit_NeoPixel。

## 9. NVS 参数掉电保存

```
#include "nvs_flash.h"
#include "nvs.h"
void storage_init(void) {  // 上电范式：错 → erase → retry
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());  // 旧数据全丢
        e = nvs_flash_init();
    }
    ESP_ERROR_CHECK(e);
}
typedef struct { int32_t thresh; char ssid[33]; } cfg_t;
void cfg_save(const cfg_t *c) {
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open("app", NVS_READWRITE, &h));  // namespace ≤15 字符
    ESP_ERROR_CHECK(nvs_set_i32(h, "thresh", c->thresh));
    ESP_ERROR_CHECK(nvs_set_str(h, "ssid", c->ssid));
    ESP_ERROR_CHECK(nvs_commit(h));  // 必须 commit 才落 flash
    nvs_close(h);
}
void cfg_load(cfg_t *c) {  // 缺省兜底；键不存在容忍
    nvs_handle_t h;
    c->thresh = 100; c->ssid[0] = 0;
    if (nvs_open("app", NVS_READONLY, &h) == ESP_OK) {
        nvs_get_i32(h, "thresh", &c->thresh);  // 不存在返回 ESP_ERR_NVS_NOT_FOUND
        size_t n = sizeof(c->ssid); nvs_get_str(h, "ssid", c->ssid, &n);
        nvs_close(h);
    }
}
```

坑：忘 commit 掉电即丢；ESP_ERR_NVS_NOT_FOUND 属常态；u8/blob 用 `nvs_set_u8/nvs_set_blob`；Wi-Fi 自身用 NVS，本函数须在 `esp_wifi_init()` 前。Arduino：`Preferences`（begin/putInt/getInt/putString）。

## 10. gptimer 周期中断

```
#include "driver/gptimer.h"
static volatile bool s_tick;
static bool IRAM_ATTR on_alarm(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *ctx) {
    *(volatile bool *)ctx = true;  // 只置标志，勿长处理
    return false;  // true=请求 yield
}
void tick_init_1ms(void) {
    gptimer_config_t tim = { .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP, .resolution_hz = 1000000 };  // 1 tick=1us
    gptimer_handle_t h;
    ESP_ERROR_CHECK(gptimer_new_timer(&tim, &h));
    gptimer_alarm_config_t alarm = { .alarm_count = 1000, .reload_count = 0,
        .flags.auto_reload_on_alarm = true };  // 1000us=1ms 周期
    ESP_ERROR_CHECK(gptimer_set_alarm_action(h, &alarm));
    gptimer_event_callbacks_t cbs = { .on_alarm = on_alarm };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(h, &cbs, &s_tick));
    ESP_ERROR_CHECK(gptimer_enable(h));  // enable 后才能 start
    ESP_ERROR_CHECK(gptimer_start(h));
}
```

主循环轮询 `s_tick` 处理。坑：on_alarm 在中断上下文，须短、`IRAM_ATTR`，勿调非 ISR-safe API；读计数 `gptimer_get_raw_count(h,&val)`；旧 driver/timer.h（timer_group 系列）勿新写。Arduino（3.x）：`timerBegin(1000000)`+`timerAttachInterrupt`+`timerAlarm`。
