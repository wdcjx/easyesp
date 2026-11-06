/**
  ******************************************************************************
  * main_arduino.ino — Arduino 轨（arduino-esp32）骨架
  * @note    easyesp 技能模板：setup/loop + millis 非阻塞节拍 + FreeRTOS 任务示例。
  *
  *          板型选择（Tools → Board）：esp32dev / esp32-s3-devkitc-1 / esp32-c3-devkitm-1
  *          core 版本纪律：2.x 与 3.x 的 LEDDC/analogWrite API 不兼容——
  *          先确认已装 core 大版本再写 LEDC 代码（见 references/arduino-track.md 迁移表）
  *          loopTask：栈 8192 字节、优先级 1、双核板跑在 core 1（C3 在 core 0）。
  ******************************************************************************
  */
#include <Arduino.h>

#define LED_PIN 2            /* 经典 DevKit 板载 LED；S3/C3 按板改 */

/* ---------------------------------------------------------------- 板载 LED 非阻塞闪灯 */
static bool ledState = false;
static uint32_t blinkT0 = 0;

/* ---------------------------------------------------------------- FreeRTOS 任务示例 */
static TaskHandle_t s_workerHandle = nullptr;

static void workerTask(void *arg)
{
  /* 任务栈单位是字节（xTaskCreatePinnedToCore 第 3 参）；本任务 2048 字节起步 */
  for (;;) {
    /* 长活放这里；不要阻塞 loop()。队列/通知见 references/freertos-on-esp32.md */
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);                        /* 等串口桥就绪（CP2102/CH340 上电抖动） */
  Serial.println("== firmware v0.1, build " __DATE__ " " __TIME__ " ==");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  BaseType_t ok = xTaskCreatePinnedToCore(
      workerTask, "worker", 2048, nullptr, 1, &s_workerHandle, 1 /* 双核: 应用任务钉 core 1; C3 只能 0 */);
  if (ok != pdPASS) {
    Serial.println("worker task create failed");
  }
  blinkT0 = millis();
}

void loop() {
  /* 非阻塞软定时器表；loop() 自己就是循环体，里面不要再写 while(1) */
  if (millis() - blinkT0 >= 500) {
    blinkT0 = millis();
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState ? HIGH : LOW);
  }
  /* 必要让出：长忙等（等串口/等事件）必须 delay(1) 或 yield()，防 loopTask 触发 WDT */

  /* ---------------------------------------------------------------- 中断提醒（模板外）
   * attachInterrupt(digitalPinToInterrupt(PIN), isrFn, FALLING); 的 isrFn
   * 必须 IRAM_ATTR + volatile 标志 + loop 里处理；ICACHE_RAM_ATTR 是旧写法已废弃。
   *   static volatile bool s_flag = false;
   *   static void IRAM_ATTR btnIsr() { s_flag = true; }
   * 长活用任务做（上面的 workerTask），别塞进 loop。
   * ------------------------------------------------------------------ */
}
