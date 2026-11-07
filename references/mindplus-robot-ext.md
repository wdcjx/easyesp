# Mind+ 教育机器人扩展库（瑞龙 ESP32-E IOT Robot 转写）

> 何时读：涉及 Mind+（DFRobot 图形化编程）用户扩展库开发、教育机器人套件（瑞龙制造 ESP32-E）、MCPWM 驱动直流电机（H 桥）、PCNT 正交编码器计数、FPV 遥控器 UART 协议、I2C 计分器读值时读本文。
> 状态：实战档——源自用户提供的已上板工程（Mind+ 扩展库 V0.0.2，含 fireBeetleEsp32E 编译产物实证），本文为源码转写、未在本机二次复测；MCPWM/PCNT 原生 API 以 ESP-IDF 官方文档为准。

## 1. 项目定位与结构

源工程：瑞龙制造（RuilongMaker）ESP32 物联网机器人板的 Mind+ 用户扩展库（MIT，gitee.com/ruilongmaker/ext-esp32iotrobot）。Mind+ 是 Scratch 系图形化编程 IDE，用户库把「积木块」翻译成 Arduino C++ 代码后本地编译烧录。

| 组成 | 文件 | 作用 |
|---|---|---|
| 清单 | `config.json` | `id`/`version`/`asset.arduinoC`（`board: ["firebeetleesp32e","firebeetleesp32"]`，`main: main.ts`） |
| 代码生成器 | `arduinoC/main.ts` | TypeScript，每个积木一个函数，用 `Generator.addInclude/addObject/addSetup/addCode` 四段式拼出 .ino |
| 管脚白名单 | `arduinoC/_menus/*.json` | 每块板一个下拉菜单定义（管脚/串口/模式枚举），IDE 端限选 |
| 库打包 | `arduinoC/libraries/libraries.zip` | 内嵌 Arduino 库源码，随扩展一起分发 |
| 发布包 | `*.mpext` | ZIP 改后缀（PK 魔数），含上述全部 |
| 案例文件 | `*.mp` | ZIP：Scratch 块 JSON（project.json）+ 资源 + **内嵌一份当时版本的扩展库** |

**关键事实**：`.mp` 案例内嵌扩展库副本（本项目实测：综合测试.mp 内嵌 V0.0.1 旧库），升级已安装扩展不会回填旧案例——详见坑 #99。

## 2. MCPWM 直流电机驱动（RL_ESP32_Motor）

MCPWM 是 ESP32 专电机控制 PWM 外设（经典 ESP32：2 unit × 3 timer × 2 operator = 12 路），Arduino 轨可直接调 IDF legacy API（`driver/mcpwm.h`）。库把 6 个「电机组」映射到硬件：

| 组号 | UNIT | TIMER | 输出对 |
|---|---|---|---|
| 1 | 0 | 0 | MCPWM0A/0B |
| 2 | 0 | 1 | MCPWM1A/1B |
| 3 | 0 | 2 | MCPWM2A/2B |
| 4 | 1 | 0 | MCPWM0A/0B |
| 5 | 1 | 1 | MCPWM1A/1B |
| 6 | 1 | 2 | MCPWM2A/1B |

初始化（管脚 A=方向脚、管脚 B=速度脚，接 H 桥双输入）：

```cpp
#include "driver/mcpwm.h"
// 每组：
mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0A, direPin);   // 信号→GPIO 映射
mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0B, speedPin);
mcpwm_config_t pwm_config = {
    .frequency = 20000,        // 源码写 50 且注释写 500——均为坑，见 #94
    .cmpr_a = 0, .cmpr_b = 0,
    .counter_mode = MCPWM_UP_COUNTER,
    .duty_mode = MCPWM_DUTY_MODE_0,   // 高电平有效
};
mcpwm_init(MCPWM_UNIT_0, MCPWM_TIMER_0, &pwm_config);
```

符号-幅值换向（sign-magnitude，速度 -100~100）：

```cpp
void Motor_Speed(float duty) {
    if (duty > 0) {          // 正转：A 恒低，B 调 PWM
        mcpwm_set_signal_low(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A);
        mcpwm_set_duty(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_B, duty);
        mcpwm_set_duty_type(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_B, MCPWM_DUTY_MODE_0);
    } else if (duty == 0) {  // 停止：双输出恒高（多数 H 桥=刹车，非滑行），见 #95
        mcpwm_set_signal_high(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A);
        mcpwm_set_signal_high(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_B);
    } else {                 // 反转：B 恒低，A 调 PWM
        mcpwm_set_signal_low(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_B);
        mcpwm_set_duty(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, -duty);
        mcpwm_set_duty_type(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, MCPWM_DUTY_MODE_0);
    }
}
```

另有 `Motor_SpeedAB(dutyA, dutyB)` 原始双占空（locked-antiphase 变体可用它实现）。**迁移注记**：legacy `driver/mcpwm.h`（`mcpwm_init/mcpwm_set_duty` 系）在 IDF 5.2+ 标记 deprecated、推荐 `driver/mcpwm_pwm.h` 新 API（`mcpwm_new_timer/mcpwm_new_operator/mcpwm_operator_connect_timer/mcpwm_new_comparator`）；arduino-esp32 2.x/3.x 下 legacy 仍可编译。以官方文档为准。

## 3. 正交编码器 PCNT 硬件计数（ESP32Encoder 库）

ESP32Encoder 库用 **PCNT 脉冲计数外设**（非 GPIO 中断软件计数）：免 CPU、硬件四倍频解码、自带毛刺滤波器。经典 ESP32 有 8 个 PCNT unit（每 unit 2 通道）。

| 模式（积木枚举） | PCNT 配置 | 说明 |
|---|---|---|
| `attachSingleEdge(a,b)` | CH0：neg_mode=COUNT_INC，pos_mode=single?DIS:DEC；CH1 全禁 | 单边沿计数，分辨率 ×1 |
| `attachHalfQuad(a,b)` | CH0 同上；CH1：pos=DIS/neg=DEC，KEEP/REVERSE | 半周期，分辨率 ×2 |
| `attachFullQuad(a,b)` | CH0+CH1 全配置 KEEP/REVERSE | 四倍频，分辨率 ×4 |

典型用法：

```cpp
#include <ESP32Encoder.h>
ESP32Encoder encoder;
encoder.attachFullQuad(32, 33);   // setup() 里
long n = (long)encoder.getCount(); // loop() 里随时读
encoder.setCount(0);               // 清零
encoder.clearCount(); encoder.pauseCount(); encoder.resumeCount();
```

实现要点（读源码得）：PCNT 计数寄存器 16 位有符号，库开 H_LIM/L_LIM 溢出中断在中断里 `pcnt_counter_clear` 软件扩展位宽；`getCount()` 在读到 PCNT 中断挂起时会二次读取规避竞态（源码注释引 IDF ref_clock 同款手法）；可选 `always_interrupt` 模式设 ±1 阈值事件做逐计数回调（`attachInterrupt`），以及 `setFilter(value)` → `pcnt_set_filter_value/pcnt_filter_enable` 硬件毛刺滤波（APB 时钟周期单位）。**迁移注记**：legacy `driver/pcnt.h` 在 IDF 5.2+ 同样有新 API（`driver/pcnt_new.h`，`pcnt_new_unit/pcnt_new_channel`），Arduino 轨仍以 legacy 为主。

## 4. FPV 遥控器 UART 协议（RL_FPV_MP）

FPV 图传遥控器（一体摄像头+遥控屏）经 19200 波特硬串口下发 8 字节定长帧：

| 字节 | 含义 |
|---|---|
| 0 | 帧头 `0x66` |
| 1–4 | 四个摇杆轴字节：RX/RY/LX/LY（顺序见下） |
| 5 | 命令位域（见下） |
| 6 | 校验：字节 1–5 逐字节异或（源码 `a^b^c^d^e&0xff` 有优先级瑕疵但字节场景无害，见 #97） |
| 7 | 帧尾 `0x99` |

通道索引（`FpvReadByte(ch)`）：0=右摇杆X、1=右摇杆Y、2=左摇杆Y、3=左摇杆X；摇杆值 **1–128–255，128=中位**（遥控器上可切 100%/60%/30% 行程，中位恒 128）。命令位：bit0 一键起飞、bit1 一键降落、bit2 紧急停止、bit4 无头模式、bit7 陀螺仪校正——**脉冲语义：先置 1 约 1 秒后自动置 0**（无头模式为翻转语义），轮询环阻塞超约 1 秒会丢命令（#98）。

解析模式（`peek()+readBytes` 逐字节对齐帧头）：

```cpp
FPV fpvSerial;
fpvSerial.begin(&Serial2, 23, -1);   // RX=23，无 TX
while (Serial2.available() >= 8) {
    if (Serial2.peek() != 0x66) { Serial2.read(); continue; }  // 丢一字节再试
    uint8_t buf[8]; Serial2.readBytes(buf, 8);
    if (buf[7] == 0x99 && checksum_ok(buf)) { /* buf[1..5] = 轴值+命令 */ }
}
```

版本差异：V0.0.1 的 `FpvReadByte` 无 bit4/bit7 分支（无头/校正读不到），V0.0.2 补齐（#99）；`index>8` 无默认返回值是 UB（#96）。

## 5. 舵机与 I2C 计分器

```cpp
// 舵机（Mind+ 用 DFRobot_Servo，等价 Servo）
#include <DFRobot_Servo.h>
Servo servo_27;
servo_27.attach(27);            // setup()
servo_27.angle(abs(90));        // 生成器对角度包 abs()，防负值

// I2C 计分器（比赛计分模块，地址 0x51、分数寄存器 0x20）
#include <RL_ScoreReader.h>
ScoreReader score;              // 默认 (0x51, 0x20)，构造可改
score.begin();                  // 内部 Wire.begin()
uint8_t s = score.getScore();   // 写寄存器地址→requestFrom(1 字节)
bool ok = score.isReadSuccess();
```

`getScore()` 忽略 `endTransmission()` 返回值（无 ACK 校验）——通用坑，见 known-pitfalls #55。

## 6. PID（RL_PID，Brett Beauregard Arduino PID 移植）

```cpp
#include <RL_PID.h>
PID myPID(const_cast<float*>(&Input), const_cast<float*>(&Output),
          const_cast<float*>(&Setpoint), 2, 5, 1, DIRECT);
myPID.SetMode(AUTOMATIC);        // setup()
// loop() 按固定节拍：
myPID.Compute();                 // 采样时间内才真算
myPID.SetOutputLimits(0, 255);   // 输出限幅（对 PWM 占空比）
myPID.SetSampleTime(100);        // ms
myPID.SetTunings(kp, ki, kd);    // 运行中改参
```

图形块把用户变量按 `double` 生成、库要 `float*`，生成器用 `const_cast` 强转绑定——文本工程直接声明 `float Input, Output, Setpoint` 即可，无需强转。与 realtime-control.md §6 的自写 PID 互补：库版省事但黑盒（无 dt 守卫/微分滤波），高频控制环（≥250Hz）建议自写。

## 7. Mind+ 扩展库开发要领（main.ts 生成器）

每个积木一个导出函数，四段式注入（键去重——同键后写覆盖先写，见 #100）：

```typescript
//% block="…" blockType="command|reporter"   ← 积木文案与类型
//% PIN.shadow="dropdown" PIN.options="PIN_DigitalWrite"  ← 参数 UI
export function My_Block(parameter: any, block: any) {
    Generator.addInclude('key', '#include <Lib.h>');   // .ino 头部
    Generator.addObject('key', 'Type ', 'name(args);');// 全局对象
    Generator.addSetup('key', 'name.begin();');        // setup()
    Generator.addCode(`name.run(${parameter.X.code});`);// loop() 处
}
```

`_menus/firebeetleesp32e.json` 定义 ESP32-E（FireBeetle）管脚白名单：**可写脚** 0,2,4,5,12–19,21–23,25–27,32,33；**可读脚**另加 34,35,36,39（input-only）；FPV 默认 Serial2+RX23、舵机默认 GPIO27。枚举用带 `//% block="中文名"` 的 enum 暴露。注意菜单把 GPIO0（boot）、18/19（VSPI 默认脚）、21/22（I2C）也列为可选——与其他外设冲突时参照 gpio-pinout-guide.md 禁区核对。

## 8. 与 skill 纪律的对照

| 图形编程场景 | 对应纪律 |
|---|---|
| forever 循环里读 FPV + 驱动电机 | 等价 loop() 轮询：不能阻塞（#98 脉冲窗）；ISR 禁清单不适用（无 ISR 生成） |
| 编码器中断模式（阈值事件回调） | PCNT ISR 上下文：回调里只做计数/置标志 |
| `Motor_Speed(0)` 期望「停」 | 刹车 vs 滑行语义按 H 桥手册确认（#95） |
| PID 积木 + 编码器积木闭环 | Compute() 节拍与传感器读取节拍一致，否则离散化失真 |

## 9. 坑位索引

本文相关坑位：#94（MCPWM 频率 50Hz）、#95（零速双高=刹车）、#96（FpvReadByte 越界 UB）、#97（校验和优先级）、#98（FPV 脉冲窗）、#99（.mp 内嵌旧库漂移）、#100（生成器同键覆盖）、#101（legacy MCPWM/PCNT API 弃用线）。详见 [known-pitfalls.md](known-pitfalls.md)。
