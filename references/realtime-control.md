# 实时控制环范式（定频循环 / PID / 姿态 / 安全状态机）

> 何时读：做定频控制（无人机/云台/平衡车/电机闭环）、传感器融合与校准、PID 与混控、失控保护等安全机制、参数持久化调参时读本文。
> 状态：实战项目沉淀（源自 ESP32 迷你无人机 Flix 中文注释版 20251226，上游 github.com/okalachev/flix，Arduino 轨 + 经典 esp32 + arduino-esp32 3.x 写法；未在本机复测）。

## 1. 架构选型：三种节拍源

| 方案 | 做法 | 适用 | 风险 |
|---|---|---|---|
| **传感器节拍（本文主线）** | `imu.waitForData()` 阻塞在 IMU 1kHz 数据就绪上，全环被动同步 | 单传感器驱动的紧闭环 | 等待实现须有界（见 §9 纪律注） |
| 定时器 ISR + 标志 | gptimer/hw_timer ISR 只置标志，任务轮询（见 peripheral-recipes.md §10） | 采样与控制解耦、多传感器 | ISR 纪律全部适用 |
| 独立高优先级任务 + vTaskDelayUntil | xTaskCreatePinnedToCore 抖动最小 | 多任务并存（遥测/日志并行） | 栈/优先级规划 |

Flix 用**单线程合作式超级循环**（跑在默认 loopTask）：无自建任务、无应用层 timer ISR，`readIMU→step→readRC→estimate→control→sendMotors→handleInput→processMavlink→logData→syncParameters` 一轮 ≈1ms。简单可审计——控制环单线程是可靠性设计，不是偷懒。

## 2. 超级循环骨架（dt 全程守卫 + Rate 子采样）

```cpp
void loop() {                       // Flix_Main20251226.ino:45
    readIMU();                      // 阻塞等 IMU 数据就绪（节拍源）
    step();                         // 更新 dt / t / loopRate
    readRC(); estimate(); control(); sendMotors();
    handleInput(); processMavlink(); logData(); syncParameters();
}
void step() {                       // time.ino:8
    float now = micros() / 1000000.0;
    dt = now - t;  t = now;
    if (!(dt > 0)) dt = 0;          // 首步/复位防 NaN
    computeLoopRate();              // 1s 窗口实测频率（CLI `time` 可查）
}
```

慢任务不做 loop 分频，用 **Rate 限速器**在主环内子采样（以全局 t 为时基）：

```cpp
class Rate { public: float rate, last = 0;        // util.h:54
    operator bool() { if (t - last >= 1 / rate) { last = t; return true; } return false; } };
static Rate mavlink10(10), log100(100), paramSync(1);   // 10Hz/100Hz/1Hz 慢环
```

要点：控制频率不靠假设——用 loopRate 实测并在调参时复核；`micros()` 时基不回绕（int64 微秒，见 freertos-on-esp32.md）。

## 3. 长流程不冻结主环（pause 模式）

校准等秒级流程不能死等：内循环持续 `step() + handleInput() + processMavlink() + delay(50)`（cli.ino:64-74），时基与命令处理持续走，仅控制/电机停摆。

## 4. IMU 校准（两件事分开做）

**陀螺偏置——静止自适应跟踪（免开机静置仪式）**：

```cpp
static Delay landedDelay(2);                      // imu.ino:75-81：静止≥2s 才开始
if (!landedDelay.update(landed)) return;
static LowPassFilter<Vector> gyroBiasFilter(0.001);   // α=0.001 超慢跟踪
gyroBias = gyroBiasFilter.update(gyro);
```

**加计——六面法（每面 1000 采样均值）**：全局 min/max → `accScale = (accMax - accMin) / 2 / ONE_G; accBias = (accMax + accMin) / 2;`（imu.ino:111-136）；校准期间切 2G 量程提灵敏度，完成后恢复工作量程。首飞 SOP：拆桨 → `ca` 六面校准 → `ps` 验证三轴水平读数 |·|≤3°。

**朝向映射单点化**：坐标变换硬编码一行 `data = Vector(data.y, -data.x, data.z);`（imu.ino:63，LFD→FLU），换板/改安装方向只改这一行，改后必须物理验证（平放三轴读数：z≈+1g，x/y≈0）。

## 5. 姿态融合：四元数互补滤波

```cpp
attitude = Quaternion::rotate(attitude, Quaternion::fromRotationVector(rates * dt)); // 陀螺积分
bool landed = !motorsActive() && fabsf(accNorm - ONE_G) < ONE_G * 0.1f;              // 落地判定
if (landed) {                                                   // 空中完全不信加计
    Vector correction = Vector::rotationVectorBetween(acc, up) * accWeight;        // accWeight=0.003
    attitude = Quaternion::rotate(attitude, Quaternion::fromRotationVector(correction));
}
attitude.normalize();
```

- 关键设计：**加计校正只在落地时做**（电机未转 + |acc|-1g<10%）——免疫振动与机动加速度；代价是空中 bias 漂移只能靠落地再校准。
- 一阶 LPF：`output += alpha * (input - output)`，`alpha = 1 - exp(-2*PI*cutOffFreq*dt)`（lpf.h:26-31）；角速率截止 ≈40Hz。
- 欧拉奇异规避：角度误差用上向量 `rotationVectorBetween(targetUp, currentUp)` 表达，不走欧拉角差。

## 6. PID 实现（三个防御点）

```cpp
float update(float error) {
    if (dt > 0 && dt < dtMax) {              // dt 守卫：首步/主环卡死时积分微分清零
        integral += error * dt;  derivative = dlpf.update((error - lastError) / dt);
        lastError = error;
    } else { integral = 0; derivative = 0; }
    return p * error + constrain(i * integral, -windup, windup) + d * derivative;  // 输出侧钳位抗饱和
}
```

- 微分对 **error** 差分（非测量值）+ LPF；抗饱和用输出侧 constrain（不截累加器，退出饱和更平滑）。
- 级联：STAB = 角度环(P) → 角速率环(PID)；ACRO 跳过角度环。统一跳过条件 `!armed || target.invalid() || thrustTarget < 0.1`——油门拉死时 PID 不积累。

## 7. 混控与电机输出

X 型四轴混控（control.ino:149-152）：

| 电机 | 公式 |
|---|---|
| FL | T + τx − τy + τz |
| FR | T − τx − τy − τz |
| RL | T + τx + τy − τz |
| RR | T − τx + τy + τz |

输出 constrain 0..1；怠速：解锁且油门<0.1 → 四电机 0.1（电机不停转，防摔桨抖动）；未解锁 memset 0。

电机用 **LEDC 78kHz/10bit**（空心杯 MOSFET 直驱；duty 0..1 → 0..1023）；换 ESC 电调则改 μs 值、频率降到 400Hz 以下。已知坑：同一 LEDC 通道刚改占空比立即再改会丢失（espressif/arduino-esp32#5306）——测试电机序列中间加 `delay(50)`（motors.ino:62）。

## 8. 安全状态机（失控保护是交付物，不是可选项）

```cpp
// 解锁手势：油门<0.05 且 yaw>0.95；上锁：yaw<−0.95（control.ino:77-78）
// RC 失控 1s → 自动缓降（safety.ino:21-35）：
if (t - controlTime > RC_LOSS_TIMEOUT) {
    mode = AUTO; attitudeTarget = Quaternion();        // 目标姿态=水平
    thrustTarget -= dt / DESCEND_TIME;                 // 10s 线性降到 0
    if (thrustTarget < 0) { thrustTarget = 0; armed = false; }
}
// 飞手夺回：AUTO 中杆量突变（油门差>0.05）→ 回 STAB（safety.ino:38-48）
```

- 未解锁电机强制清零；纯 MAVLink 飞行（无 RC）不触发 RC 失控逻辑（`controlTime==0` 判定）。
- **飞行中禁写 NVS**：擦除毫秒级阻塞 1kHz 主环 → 抽动/掉高（parameters.ino:127 原生防护：`if (motorsActive()) return;`）。
- **brownout 取舍**：电机浪涌拉低电压触发欠压复位循环 → `REG_CLR_BIT(RTC_CNTL_BROWN_OUT_REG, RTC_CNTL_BROWN_OUT_ENA);` 关闭欠压复位（util.h:39-41，仅经典 esp32 寄存器语义）。代价=失去低压保护——正确做法是硬件电源设计+软件低压报警；关 brownout 是最后手段且必须文档化。

## 9. 参数表驱动持久化（NVS）

```cpp
Parameter parameters[] = { {"CTL_R_RATE_P", &rollRatePID.p}, /* …50 项… */ };  // 名字→float* 指针表
// 启动：逐项 getFloat，键不存在用缺省回填；运行：1Hz Rate 检查脏值才写
static Rate rate(1); if (!rate) return; if (motorsActive()) return;
for (auto &p : parameters)
    if (p.value != *p.variable) { storage.putFloat(p.name, *p.variable); p.value = *p.variable; }
```

- Preferences 命名空间如 "flix"；**键名 ≤15 字符**（NVS 限制）；CLI `p <name> <value>` 调参与 MAVLink PARAM_SET 共用 setParameter 入口。
- 调参链路统一（CLI/MAVLink/上电回填）是量产工程的基本功：一处定义，处处同源。

## 10. 遥测与地面站（WiFi AP + UDP + MAVLink）

`WiFi.softAP("Drone_WiFi","12345678")` + `udp.begin(14550)`：MAVLink 走 UDP 广播 255.255.255.255:14550，收到首包后改单播（wifi.ino:26-31）。最小子集：HEARTBEAT 1Hz、姿态/RC/IMU 10Hz、MANUAL_CONTROL 杆量、PARAM_* 调参、COMMAND_LONG 解锁+ACK。手机杆量直接作控制输入（mavlink.ino:96-107）。

## 11. 与本技能纪律的对照

- `imu.waitForData()` 是**有界的传感器节拍等待**（等待实现依赖库内部，若为自旋必须带超时/让出）——本技能「每个硬件等待必须有超时」约束仍适用，dt 守卫（§6）是它的兜底防线。
- 超级循环跑在 loopTask：长流程用 pause 内循环 + delay(50) 让出，不让 IDLE 饿死（TWDT，见 freertos-on-esp32.md）。
- 该固件是 **arduino-esp32 3.x-only**（`ledcAttach`/`ledcWrite(pin,duty)`，2.x 反而编译失败）——LEDC API 必须按已装 core 大版本写（硬约束，见 arduino-track.md 迁移表）。
