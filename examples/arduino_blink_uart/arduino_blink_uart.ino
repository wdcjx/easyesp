/*
  arduino_blink_uart — Arduino 轨（arduino-esp32 3.x）最小可编译例程

  LED_BUILTIN 非阻塞闪烁 + Serial 心跳；millis() 时基，loop() 不阻塞。
  CI：.github/workflows/build.yml 用 arduino-cli（core 3.3.12 锁版本）
  以 esp32 / esp32s3 / esp32c3 三块板编译本 sketch。
*/

#ifndef LED_BUILTIN
#define LED_BUILTIN 2   /* 兜底：无板级 LED_BUILTIN 定义的 core 用 GPIO2 */
#endif

static uint32_t s_last_flip = 0;   /* 上次电平翻转时刻（millis） */
static uint32_t s_last_beat = 0;   /* 上次心跳打印时刻（millis） */
static bool s_led = false;

void setup()
{
    Serial.begin(115200);
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    Serial.println("arduino_blink_uart start");
}

void loop()
{
    uint32_t now = millis();
    if (now - s_last_flip >= 500) {          /* 500ms 翻转一次 LED */
        s_last_flip = now;
        s_led = !s_led;
        digitalWrite(LED_BUILTIN, s_led ? HIGH : LOW);
    }
    if (now - s_last_beat >= 5000) {         /* 5s 一次心跳，证明没死 */
        s_last_beat = now;
        Serial.println("alive");
    }
}
