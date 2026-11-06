/**
  ******************************************************************************
  * @file    main_idf.c
  * @brief   ESP32（esp32/S3/C3 通用）ESP-IDF 5.3.x 工程骨架
  * @note    easyesp 技能模板：app_main + NVS + ESP_LOG + 非阻塞主循环
  *          （对应 STM32 模板的 SysTick 毫秒节拍，这里用 esp_timer_get_time 微秒时基）。
  *
  *          工程配置要点：
  *          - 新工程：idf.py create-project → set-target esp32|esp32s3|esp32c3
  *          - main/CMakeLists.txt 需要 REQUIRES：driver nvs_flash esp_timer
  *          - 日志走 UART0（GPIO1/3，115200），idf.py monitor 直接看
  *          - sdkconfig 只提交 sdkconfig.defaults，见 templates/sdkconfig.defaults
  *
  *          注意：单独把本文件放在本目录打开时，
  *          "无法打开源文件 driver/gpio.h" 属预期现象——头文件在 IDF 里，
  *          放入实际工程（idf.py build）后即消除。
  ******************************************************************************
  */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"

static const char *TAG = "main";

/* Private define ------------------------------------------------------------*/
#define LED_PIN     GPIO_NUM_2      /* 经典 ESP32 DevKit 板载 LED；S3/C3 按板改 */
#define LED_ON(x)   gpio_set_level(LED_PIN, x)

/* Private variables ---------------------------------------------------------*/

/* Private function prototypes -----------------------------------------------*/
static void led_init(void);
static esp_err_t nvs_init_safe(void);

/**
  * @brief  微秒时基（int64_t，永不过期）。替代 STM32 millis()/micros()
  */
static inline int64_t now_us(void) { return esp_timer_get_time(); }

/**
  * @brief  主函数：初始化顺序 = NVS → 外设 → （网络最后，见 wifi-networking.md）
  */
void app_main(void)
{
    ESP_ERROR_CHECK(nvs_init_safe());   /* NVS 最先：WiFi/参数保存都依赖它 */
    led_init();

    ESP_LOGI(TAG, "== firmware v0.1, build " __DATE__ " " __TIME__ " ==");

    int64_t blink_t0 = now_us();
    bool led_state = false;
    while (1) {
        /* ---- 非阻塞软定时器表：要更多节拍就加行（对齐 STM32 millis() 模式）---- */
        if (now_us() - blink_t0 >= 500 * 1000) {    /* 500ms 翻转 */
            blink_t0 = now_us();
            led_state = !led_state;
            LED_ON(led_state);
        }
        /* ---- 必须让出：防 Task WDT（忙循环让出是硬约束）---- */
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

static void led_init(void)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << LED_PIN,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&io);
    gpio_set_level(LED_PIN, 0);     /* 复位后先灭灯 */
}

/**
  * @brief  NVS 初始化标准范式（损坏则擦除重试）；网络工程必须最先跑
  */
static esp_err_t nvs_init_safe(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    return err;
}

/**
  ******************************************************************************
  * 中断服务函数集中区（示例：GPIO 按键，按需添加）
  * 铁律见 references/isr-and-concurrency-rules.md：
  *   - handler 必须 IRAM_ATTR；内只置标志/FromISR API；禁 printf/ESP_LOG/vTaskDelay
  *   - gpio_install_isr_service(ESP_INTR_FLAG_IRAM) 与 IRAM_ATTR 联动
  ******************************************************************************
  */
/* #define USE_BUTTON_ISR */
#ifdef USE_BUTTON_ISR
#include "driver/gpio.h"
#define BTN_PIN GPIO_NUM_0
static volatile bool s_btn_pressed = false;   /* ISR 共享：必须 volatile */

static void IRAM_ATTR btn_isr_handler(void *arg)
{
    (void)arg;
    s_btn_pressed = true;                     /* 只置标志，主循环处理 */
}
#endif

static void button_isr_init(void)             /* 参考实现，用再启用 */
{
#ifdef USE_BUTTON_ISR
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << BTN_PIN,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .intr_type    = GPIO_INTR_NEGEDGE,
    };
    gpio_config(&io);
    ESP_ERROR_CHECK(gpio_install_isr_service(ESP_INTR_FLAG_IRAM));
    ESP_ERROR_CHECK(gpio_isr_handler_add(BTN_PIN, btn_isr_handler, NULL));
#endif
}
