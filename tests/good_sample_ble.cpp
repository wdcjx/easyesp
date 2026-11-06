/* 正例：BLE HID 正确纪律（配合 validate_esp_generated.py 自测）
 * ISR 只置 volatile 标志；BLE API 全部在任务上下文；回调只做状态翻转
 */
#include <stdbool.h>
#include <stdint.h>

typedef struct BLEServer BLEServer;
class BleAdvertising { public: void start(); };
extern BleAdvertising g_adv;

volatile bool g_batt_evt = false;
volatile uint8_t g_batt_pct = 100;
static bool g_connected = false;

/* ---- ISR：只置标志，无任何 BLE/阻塞调用 ---- */
void IRAM_ATTR batt_sample_isr(void) {
    g_batt_evt = true;
}

/* ---- BLE 回调：短处理（状态翻转+重启广播），无阻塞无堆 ---- */
class ServerCallbacks {
public:
    void onConnect(BLEServer *pServer) {
        (void)pServer;
        g_connected = true;
    }
    void onDisconnect(BLEServer *pServer) {
        (void)pServer;
        g_connected = false;
        g_adv.start();                        /* 任务上下文允许重启广播 */
    }
};

/* ---- 任务：BLE 协议栈调用全部在这里 ---- */
void ble_task(void *arg) {
    (void)arg;
    for (;;) {
        if (g_batt_evt) {
            g_batt_evt = false;
            /* hid.setBatteryLevel(g_batt_pct); -- BLE 调用在任务上下文，允许 */
        }
        vTaskDelay(pdMS_TO_TICKS(50));        /* 任务节拍让出 */
    }
}
