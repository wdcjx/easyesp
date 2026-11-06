# BLE HID 键盘（Arduino 轨）

> 何时读：做 BLE HID 设备（键盘/媒体键/遥控器）、BLE 从机广播与配对、按键扫描去抖、BLE 电量上报时读本文。
> 状态：实战项目沉淀（源自**已上板量产固件**「ESP32-C3 BLE Keybrick」，源工程在真实硬件长期运行；构建于 arduino-esp32 2.x 经典 BLE 库，本文为源码转写、未在本机二次复测。3.x 迁移建议对齐官方迁移指南与 NimBLE-Arduino 文档为准）。

## 1. 库选型（先定库再写代码）

| 库 | 随附方式 | 适用 | API 前缀 |
|---|---|---|---|
| 经典 BLE（Bluedroid 封装） | arduino-esp32 **2.x 内置**（`<BLEDevice.h>` 等）；**3.x 起从核心移除** | 维护 2.x 旧工程 | `BLEDevice::` / `BLEHIDDevice` |
| NimBLE-Arduino（h2zero，第三方） | lib_deps 安装，2.x/3.x 均可用 | **新项目推荐**（省内存约 50%+） | `NimBLEDevice::` / `NimBLEHIDDevice` |

- 本机注记：Arduino15 已装 esp32 core **2.0.11**（含经典 BLE 库可直接编译）；PlatformIO 无本机包缓存。
- ESP-IDF 轨 BLE（Bluedroid/NimBLE 原生 API）**未沉淀**，以官方文档为准。

## 2. BLE HID 初始化铁律序列（顺序敏感，错序主机不识别）

在**独立 FreeRTOS 任务**里建栈（BLE 栈本身吃任务栈，实测工程给 20000 字节、优先级 5）：

```cpp
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>

void taskServer(void *pv) {
    BLEDevice::init("Keybrick");                 // 1 设备名
    BLEServer *pServer = BLEDevice::createServer();
    pServer->setCallbacks(&s_connStatus);        // 连接/断开回调
    BLEHIDDevice *hid = new BLEHIDDevice(pServer);
    // 2 输入/输出报告：键盘 REPORT_ID=1、媒体键 REPORT_ID=2
    s_inputKb  = hid->inputReport(KEYBOARD_ID);
    s_outputKb = hid->outputReport(KEYBOARD_ID); // 主机 LED 输出
    s_inputMd  = hid->inputReport(MEDIA_KEYS_ID);
    s_outputKb->setCallbacks(&s_ledCb);          // 可省：不关心 CapsLock 等可不挂
    hid->manufacturer()->setValue("xxx");
    hid->pnp(0x02, 0xe502, 0xa111, 0x0210);      // 来源/厂商/产品/版本
    hid->hidInfo(0x00, 0x01);
    BLESecurity *sec = new BLESecurity();
    sec->setAuthenticationMode(ESP_LE_AUTH_BOND);// 仅绑定，无 MITM（键盘无屏无键盘输入能力）
    hid->reportMap(s_reportMap, sizeof(s_reportMap)); // 3 报告描述符
    hid->startServices();                        // 4 启动 HID/设备信息/电量三服务
    hid->setBatteryLevel(100);                   // 5 电量初值
    BLEAdvertising *adv = BLEDevice::getAdvertising();
    adv->setAppearance(HID_KEYBOARD);            // 6 广播外观
    adv->addServiceUUID(hid->hidService()->getUUID());
    adv->addServiceUUID(hid->deviceInfoService()->getUUID());
    adv->addServiceUUID(hid->batteryService()->getUUID());
    BLEDevice::startAdvertising();
    vTaskDelay(portMAX_DELAY);                   // 7 任务留住，勿删
}
void begin() { xTaskCreate(taskServer, "server", 20000, nullptr, 5, nullptr); }
```

NimBLE 对应：`NimBLEDevice::init` → `NimBLEHIDDevice`，inputReport/outputReport/reportMap/startServices/setBatteryLevel 语义一一对应；`setSecurityAuth(true,false,false)` 替代 setAuthenticationMode。

## 3. 报告描述符（8 字节引导键盘 + Consumer 媒体键）

- 键盘报告：8 字节 = 修饰键 1B（bit0=LeftCtrl…bit5=RightGUI）+ 保留 1B + 键码 6B；输出报告 5bit LED。
- 媒体报告：Consumer 页（0x0C）16bit 位图：0xB5 Next / 0xB6 Prev / 0xB7 Stop / 0xCD Play/Pause / 0xE2 Mute / 0xE9 Vol+ / 0xEA Vol-。
- 描述符字节数组较长（约 80 行），照 USB HID Usage Table 标准写；细节以实战工程/标准文档为准，不凭记忆编造。

## 4. 发送按键与两个真实坑

```cpp
void send2Ble(const uint8_t *keys8) {       // 8 字节键盘报告
    if (!s_connected) return;               // 未连接直接丢，防阻塞
    s_inputKb->setValue((uint8_t *)keys8, 8);
    s_inputKb->notify();
}
```

- **坑 A（REPORT_ID 约定）**：经典 BLEHIDDevice 多报告时 notify 负载**不带 Report ID 前缀**（描述符里已声明 REPORT_ID）；乱加前缀导致 Windows/Android 直接失灵。跨平台（macOS/iOS）须实测。
- **坑 B（模式切换卡键）**：切换工作模式/进入配置前**先发全零空报告**（`uint8_t release[8] = {0}; send2Ble(release);`），否则主机认为按键长按不放——实战项目每个模式切换点都这么做。

## 5. 连接管理（断线必须重启广播）

```cpp
class ConnStatus : public BLEServerCallbacks {
    void onConnect(BLEServer *p) override {
        s_connected = true;
        // 经典库：对 0x2902 (CCCD) setNotifications(true)；NimBLE 自动管理，此步可删
    }
    void onDisconnect(BLEServer *p) override {
        s_connected = false;
        p->getAdvertising()->start();       // 铁律：断线后重启广播，否则永远搜不到
    }
};
```

- 实战反例：源工程 onDisconnect 未重启广播，作者留 TODO「How to reconnect automatically?」，设备断一次就隐身——**这是 BLE 外设最常见坑**。
- BLE 回调运行在 BLE 栈任务上下文（铁律 B：任务上下文）——只置标志/短操作，禁 vTaskDelay/串口大打印/堆分配。

## 6. 按键扫描 + 去抖 + 长短按（与 BLE 解耦）

```cpp
// 硬件定时器 10ms 只采样置标志（ISR 瘦身）：
void IRAM_ATTR onTimer() { for (i…) s_raw[i] = digitalRead(BTN[i]); }  // 实际项目 ISR 只置标志
// loop/任务侧：双读 + delay(5) 去抖；millis 长按窗口：
static uint32_t t0; if (now - t0 >= 2000) { /* 长按事件 */ }
// 事件一次性触发：置 shouldSend 标志，发出后清；isReleased 复位——防「按一下连发」
```

- 独立按键 active-low 时用 `pinMode(pin, INPUT_PULLUP)`（实战工程依赖外部上拉、裸 INPUT，复刻硬件缺上拉会浮空误触发）。
- C3 注意 GPIO8/GPIO9 为 strapping 引脚（见 gpio-pinout-guide.md），按键尽量避开。

## 7. 电量采集与 BLE 上报

```cpp
// 周期任务（勿在 ISR 调 BLE API——实战项目在 60s 硬件定时器 ISR 里直调 setBatteryLevel，反面教材）：
uint32_t raw = analogRead(PIN_VBAT);                 // 分压电阻采样
float v = raw * 2.878 / 4096.0f / 0.6357f;           // 分压比换算（按实际电阻算）
int pct = (int)((v - 2.64f) / (4.20f - 2.64f) * 100); // 线性估算，锂电仅近似
pct = constrain(pct, 0, 100);
hid->setBatteryLevel(pct);                            // BAS 服务 notify
```

采集周期 10s、上报周期 60s 分开；低电（如 <3.3V）降外设功耗（屏幕亮度/广播间隔）。

## 8. arduino-esp32 2.x → 3.x 迁移对照（BLE 工程相关）

| 2.x 写法 | 3.x 状态 | 3.x 替代 |
|---|---|---|
| `<BLEDevice.h>` 经典 BLE 库 | **从核心移除** | NimBLE-Arduino（API 改 NimBLEDevice::/NimBLEHIDDevice）；或单独安装经典库源 |
| `ESP_LE_AUTH_BOND` | 随经典库 | `NimBLEDevice::setSecurityAuth(bond, mitm, lesc)` |
| 0x2902 CCCD 手动 setNotifications | 随经典库 | NimBLE 自动管理，删掉 |
| `timerBegin(0, 80, true)` + `timerAlarmWrite(t, us, true)` + `timerAlarmEnable(t)` | **已删除** | `timerBegin(1000000)` + `timerAttachInterrupt(t, &fn)` + `timerAlarm(t, us, true, 0)`（分辨率 1MHz 定死，见 arduino-track.md） |
| `<driver/adc.h>` | 弃用 | adc_oneshot（analogRead 不受影响） |
| Preferences / tone / IRAM_ATTR | 兼容 | 不变 |

## 9. 纪律清单（BLE 工程自检）

- [ ] BLE 建栈在独立任务（≥20000 字节栈），不在 setup() 里同步建完
- [ ] onDisconnect 重启广播；未连接时 send 直接丢
- [ ] BLE 回调只置标志；ISR 禁调任何 BLE API
- [ ] 模式切换先发空报告；事件一次性触发防连发
- [ ] 媒体键走 Consumer 报告（独立 REPORT_ID），与键盘报告分开发送
- [ ] ISR↔loop 共享变量 volatile + 读写方向单一；多字节共享用临界区（铁律见 isr-and-concurrency-rules.md）
- [ ] 2.x/3.x 与库版本在交付说明中声明；REPORT_ID 约定跨平台实测后才交付
