# 力反馈旋钮（simpleFOC + AS5600 + LVGL 圆屏 + BLE HID）

> 何时读：做无刷电机力反馈旋钮/触感旋钮（SmartKnob 类）、圆屏 GC9A01 UI、或用 LVGL 编码器组做「旋钮选单」交互；也适用于任何「电机力矩环 + RTOS 任务分工」的组合。
> 状态：知识沉淀（源工程 super_knob 已上板；API 对齐 SimpleFOC 2.2.x / LVGL 8.2 / arduino-esp32 4.1.x）

## §1 定位与硬件

| 项 | 值 |
|---|---|
| 源工程 | super_knob（2022，PlatformIO+Arduino，board `pico32`=经典 ESP32） |
| 形态 | 磁吸底座力反馈旋钮：5 种触感档 + IoT 中控菜单 + BLE 媒体键 + WS2812 灯效 |
| 平台 | `platform = espressif32 @ ~4.1.0`，分区 `huge_app.csv`（3MB app：LVGL+图片字库），upload 921600 |
| lib_deps | Simple FOC 2.2.1 / LVGL ^8.2.0 / TFT_eSPI ^2.4.70 / ESP32 BLE Keyboard ^0.3.2 / Adafruit NeoPixel ^1.10.5 |

引脚（经典 ESP32）：

| 功能 | 引脚 | 备注 |
|---|---|---|
| 电机三相 PWM | 22 / 4 / 5 | BLDCDriver3PWM |
| 驱动器使能 EN | 21 | `pinMode(21,OUTPUT)` + HIGH 才有力 |
| AS5600 I2C | SDA 19 / SCL 18，400kHz | `TwoWire(0)`，地址 0x36 |
| 圆屏 GC9A01 240×240 | SPI（TFT_eSPI 配） | 见 §6，`User_Setup.h` 必须手改 |
| WS2812 ×4 | 11 | `NEO_GRB + NEO_KHZ800` |
| 触摸键 | 33 / 32 / 12 | 只用 PIN1=33 做退出 |
| 供电 | 12V 驱动 + 5V 逻辑 | 共地；电机与 MCU 分电源更稳 |

## §2 任务与并发结构

```cpp
setup(): pinMode(21,OUTPUT) HIGH → Serial/Serial1 115200 → ble_keyboard_init()
        → 4 个队列(深度10, 元素=指针) → WS2812_init()
        → Task_foc(4096,P2,C1) Task_lvgl(4096,P3,C0) Task_module(2048,P4,C1) Task_ws2812(1024,P4,C1)
loop(): delay(10000);   // Arduino 任务空转
```

| 任务 | 栈 | 优先级 | 核 | 职责 |
|---|---|---|---|---|
| Task_foc | 4096 | 2 | 1 | 初始化电机 → 力矩环 1kHz 循环 + 触感算法 |
| Task_lvgl | 4096 | 3 | 0 | `lv_task_handler()` 独占 LVGL + 渲屏 |
| Task_module | 2048 | 4 | 1 | 阻塞等队列，串口透传（预留涂鸦模组） |
| Task_ws2812 | 1024 | 4 | 1 | 灯效状态机 |

**跨任务只走队列**：LVGL 事件回调里 `update_motor_config(n)` + `update_page_status(CHECKOUT_PAGE)` 通知 FOC；FOC 初始化阶段 `update_motor_status(MOTOR_INIT/SUCCESS/END)` 反推 LVGL 进度条。

> 队列元素是**指针**（`sizeof(struct _knob_message *)`），消息体是全局单例——省内存但要求「拷贝语义」自律，见坑 #195。

## §3 simpleFOC 初始化流水（顺序即依赖）

```cpp
update_motor_status(MOTOR_INIT);
I2Cone.begin(19, 18, 400000UL);      // AS5600
sensor.init(&I2Cone);  motor.linkSensor(&sensor);
driver.voltage_power_supply = 12;
driver.init();         motor.linkDriver(&driver);
motor.voltage_sensor_align = 3;      // 对齐电压（伏）
motor.foc_modulation = FOCModulationType::SpaceVectorPWM;
motor.controller = MotionControlType::angle;   // 先角度环再切力矩
motor.PID_velocity.P = 0.08; I = 4; D = 0.0002;
motor.LPF_velocity.Tf = 0.02; motor.P_angle.P = 20; motor.velocity_limit = 5;
motor.useMonitoring(Serial);
motor.init(); motor.initFOC();       // 校准电角度 + 传感器方向
update_motor_status(MOTOR_INIT_SUCCESS);
init_angle();                        // 电压线性缓升到 volt_limit，避免上电猛甩
motor.controller = MotionControlType::torque;
```

`init_angle()`：取当前角度做目标，把 `voltage_limit` 从 0 按 `volt_limit/init_smooth` 递增同时 `loopFOC()+move()`——**上电第一下不抖的关键**。

## §4 触感算法（真正值钱的部分）

每 1ms 循环（`vTaskDelay(1)`）执行：

```
loopFOC()
消费队列消息：CHECKOUT_PAGE → 重置 detent 中心 + 动态 D 插值 + 抖一下
              BUTTON_CLICK  → 抖一下
怠速检测：速度 EWMA(|v|>0.05 清零计时，否则记 idle_start)
怠速修正：闲置>500ms 且距中心<5° → 中心按 0.0005 慢追实际角
卡位推进：angle_to_center > width*snap_point (且非端点) → 中心+=width，position--
死区：dz = CLAMP(angle_to_center, ±min(width*0.2, 1°))
出界：limit=10 / P=endstop*4；否则 limit=3 / P=detent*4
速度守护：|shaft_velocity|>60 rad/s → move(0)（防正反馈失控）
否则：torque = PID_velocity(-angle_to_center + dz)
```

5 种预设（`KnobConfig` 表，切换即换手感）：

| # | 档位 | 每格角度 | detent 强度 | snap | 用途 |
|---|---|---|---|---|---|
| 0 | 无限制 | 10° | 0 | 1.1 | 连续量（音量） |
| 1 | 粗 32 档 | 8.2258° | 2 | 1.1 | 菜单/亮度，强棘轮 |
| 2 | 细 256 档有阻尼 | 1° | 1 | 1.1 | 精调 |
| 3 | 细 256 档无阻尼 | 1° | 0 | 1.1 | 顺滑滚动 |
| 4 | 开关 2 位 | 60° | 1 | **0.55** | ON/OFF，中点前翻转 |

调参经验：

| 现象 | 调哪里 |
|---|---|
| 手感「软」 | `detent_strength_unit` ↑（力矩 P 系数同步 4×） |
| 过冲/回弹 | `PID_velocity.D` ↑ 或 `LPF_velocity.Tf` ↑ |
| 卡位切换发飘 | `snap_point` ↑（>1 表示过了下一格才跳） |
| 静止时缓慢漂移 | `IDLE_CORRECTION_RATE_ALPHA` ↓ 或延迟 ↑ |
| 快速甩动被「拽住」 | 速度守护阈值 60 太低，按电机上限调 |

页面切换时按 `position_width` 在 3°–8° 之间线性插值 `PID_velocity.D`（`0.08×detent` → `0.02×detent` 之间 CLAMP），让粗细档各有合适的阻尼。

## §5 BLE HID 媒体键

```cpp
BleKeyboard bleKeyboard("Super Knord pro", "Espressif", 100);  // 名/厂商/电量
bleKeyboard.begin();
bleKeyboard.isConnected();                 // 未连接时先判再发
bleKeyboard.write(KEY_MEDIA_PLAY_PAUSE);   // 播放/暂停
bleKeyboard.write(KEY_MEDIA_NEXT_TRACK);   // 下一曲
```

BLE 栈本身占内存（huge_app 分区就是为它+LVGL 图片留的）；电台共存与 BLE 断连行为见 `ble-hid-keyboard.md`。

## §6 LVGL 圆屏端口（GC9A01）

| 环节 | 做法 |
|---|---|
| 驱动库 | TFT_eSPI **必须手改 `User_Setup.h`**：`#define GC9A01_DRIVER`、240×240、圆屏引脚（C3 组 MOSI3/SCLK2/CS7/DC6/RST10/BL12，非 C3 组 MOSI13/SCLK14…） |
| 缓冲 | 双缓冲 `buf_1/buf_2` 各 `240*240/4` 个 `lv_color_t` = **28.8KB/块，共 57.6KB 内部 RAM** |
| flush | `startWrite → setSwapBytes(true) → pushImageDMA → dmaWait → endWrite → lv_disp_flush_ready` |
| 输入 | `LV_INDEV_TYPE_ENCODER`，`read_cb` 每帧把 `get_motor_position()` 差分喂 `enc_diff`；按键态用触摸键 |
| 组 | `lv_group_create()` + `lv_group_set_default()` + `lv_indev_set_group()`——没有组，编码器无法操作控件 |
| 圆环菜单 | 竖向 flex 列 + `LV_SCROLL_SNAP_CENTER` + `LV_EVENT_SCROLL` 回调：按勾股定理算 x 平移 + 透明度渐变，形成环形视觉 |
| 中文字体 | `LV_FONT_DECLARE(lv_font_chinese_source_20)`，在 `lv_conf.h` 开对应字库 |
| 页面状态机 | `WELCOME / IOT_MAIN / IOT_POINTER / IOT_SENSOR / IOT_PLAYER / IOT_TOMATO_CLOCK / IOT_LIGHT_BELT / IOT_SMART_FAN / ALARM_CLOCK / ABOUT / SUPER_PAGE_BUSY` |

**LVGL 所有权铁律**：只有 `Task_lvgl` 能调 `lv_*`；其他任务通过队列传「页面号/电机状态」，LVGL 任务里再切屏。

## §7 触摸键（无 TTP223 的省料做法）

```cpp
static bool touch_pad_press(int gpio) {
    static int cnt = 0;
    if (touchRead(gpio) < 15) {            // 阈值按板实测
        if (++cnt > 4) {                   // 4 次 ≈ 10ms 消抖
            if (touchRead(gpio) < 15) { cnt = -8; return true; }  // 冷却防连击
        }
    } else cnt = 0;
    return false;
}
```

只用 `ESP32_TOUCH_PIN1(33)` 做「退出当前页」。注意它被塞进了 LVGL 的 `encoder_read` 回调——每帧都会读一次触摸。

## §8 WS2812 灯效

`Adafruit_NeoPixel(4, 11, NEO_GRB + NEO_KHZ800)`；效果：呼吸 `rainbowCycle`、整体渐变 `rainbow`、流光/反向流星（15 像素拖尾）、`colorWipe`。`Task_ws2812` 收 `WS2812_ROLL = 1` 时 suspend 呼吸任务 → 播流光 → resume。

> 这些效果内部全是 `delay()` 阻塞循环——与 FOC 同核且优先级更高（P4 > P2），播放期间力矩环被拉到 10ms 级，手感会「顿」。要正解就改成定时器驱动的非阻塞动画，见坑 #199。

## §9 迁移到 ESP-IDF 轨

| Arduino(本工程) | IDF 对应 |
|---|---|
| LVGL 手写 flush | `esp_lvgl_port` 组件（DMA flush + tick） |
| TFT_eSPI | `esp_lcd_gc9a01` 面板驱动 |
| SimpleFOC | 无官方 IDF 移植——FOC 环需自写或 vendored（SVPWM + 霍尔/编码器） |
| BleKeyboard | NimBLE HID（`ble-hid-keyboard.md` 有完整 IDF 版） |
| Arduino 队列/任务 | 原生 FreeRTOS，API 相同 |

## §10 坑位索引

| # | 一句话 |
|---|---|
| 194 | SimpleFOC 2.2.1 与 arduino-esp32 4.1.0 硬绑定 |
| 195 | 队列传指针 + 全局消息体复用 |
| 196 | `loop()` 仅 `delay(10000)`，Arduino 主任务空转 |
| 197 | `touchRead` 塞进 LVGL `encoder_read` 回调 |
| 198 | 驱动器使能 GPIO21 写死，C3 分支未区分 |
| 199 | WS2812 阻塞灯效与 FOC 同核且优先级更高 |
| 200 | TFT_eSPI `User_Setup.h` 手工补丁不入库 |
| 201 | 240×240 双缓冲占 57.6KB 内部 RAM |
| 202 | 速度 >60 rad/s 直接 `move(0)`，手感断崖 |
| 203 | 触感切换靠魔法数字 index（1/2/4） |

## 自检

- [ ] 驱动器 EN 先拉高再 `driver.init()`；电机与 MCU 共地
- [ ] `init_angle()` 电压缓升后再切 torque
- [ ] LVGL 只在单一任务内调用；其余任务只发队列
- [ ] 圆屏 flush 后 `lv_disp_flush_ready` 必调
- [ ] 触摸阈值按目标板实测标定（不同批差异大）
