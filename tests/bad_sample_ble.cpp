/* 反例：BLE HID 工程纪律（配合 validate_esp_generated.py 自测，不可用于实机）
 * 覆盖新规则：R4 BLE API 入 ISR（VIOL）、ISR 内 ->notify（WARN）、
 * R13 BLE 回调（onConnect/onDisconnect 类方法）内阻塞+堆（VIOL）
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct BLEServer BLEServer;
class BleHidDevice { public: void setBatteryLevel(uint8_t); };
class HidReport    { public: void notify(); };
extern BleHidDevice hid;
extern HidReport    keyboardReport;
#define BLEDevice_getAdvertising() ((void *)0)

/* ---- 反例 1：硬件定时器 ISR 里调 BLE 协议栈（C++ 真实形状） ---- */
volatile bool g_batt_evt = false;

void IRAM_ATTR batt_sample_isr(void) {
    g_batt_evt = true;
    BLEDevice::getAdvertising()->start();     /* VIOL: BLEDevice:: 入 ISR */
    hid.setBatteryLevel(80);                  /* VIOL: setBatteryLevel 入 ISR */
    keyboardReport.notify();                  /* WARN: ISR 内 ->notify 样式 */
}

/* ---- 反例 2：BLE 回调类方法里阻塞/堆操作 ---- */
class ServerCallbacks {
public:
    void onConnect(BLEServer *pServer) {
        vTaskDelay(100);                      /* VIOL: 回调内阻塞（BLE 协议栈任务被卡） */
        (void)pServer;
    }
    void onDisconnect(BLEServer *pServer) {
        (void)pServer;
        char *p = (char *)malloc(32);         /* VIOL: 回调内堆操作 */
        (void)p;
    }
};

void ble_setup(BLEServer *srv) {
    /* srv->setCallbacks(&serverCallbacks);    -- 注册证据行（注释态，regex 走 neutralize 前原文） */
    (void)srv;
}
