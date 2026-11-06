# 电机控制与 CAN：FOC 轮腿机器人范式（TWAI/LQR/VMC）

> 何时读：做电机控制、CAN/TWAI 总线设备、自平衡/轮腿/平衡车、LQR 或 VMC 控制律部署、MPU6050 DMP 姿态、BLE 遥控载具时读本文。
> 状态：实战项目沉淀（源自已上板工程 Skythinker foc-wheel-legged-robot，ESP32-C3 运动主控 + STM32 FOC 驱动板，双轮腿自平衡机器人已上板运行；本文为源码行为与 API 知识转写、未二次复测；源工程 GPL-3.0，本文非源码摘录）。

## 1. 系统定位与本地路径

- 源工程：`D:\ESP32project\foc-wheel-legged-robot-master\foc-wheel-legged-robot-master\`（上游 gitee.com/skythinker/foc-wheel-legged-robot / github.com/Skythinker616）。六模块：solidworks（机械）/ matlab（算法仿真）/ stm32-foc（电机驱动板，C6T6 SimpleFOC 移植）/ **esp32-controller**（运动主控）/ linux-fpv（图传）/ android（遥控 APP）。
- 分工：ESP32-C3 负责 IMU 姿态 + 平衡算法 + 目标斜坡，经 **CAN（TWAI）1Mbps** 下发电压环指令给 STM32 FOC 板；STM32 负责 FOC 电流换相与 500ms 总线离线保护。任何"算法板 + 驱动板"的双板架构可直接套这个分工。
- 物料成本（README）：不含图传约 ￥549。

## 2. 工程形态：Arduino 作为 IDF 组件混编

- `esp32-controller\software\platformio.ini`：`framework = arduino, espidf`（双框架混编，Arduino 跑在 IDF 之上），`board_build.mcu=esp32c3`、USB CDC on boot、`-O2`；lib_deps 仅 `electroniccats/MPU6050@^0.6.0`；platform 未锁版本（坑：换机重建结果不可复现，自建工程务必锁版本）。
- 入口桥接：自写 `extern "C" void app_main(){ setup(); while(1) loop(); }`（main.cpp:951-957）——IDF 工程里复用 Arduino 库的最低成本路径。
- sdkconfig 要点：`FREERTOS_HZ=1000`、USB_SERIAL_JTAG 做控制台、Bluedroid（经典 BLE 栈）。

## 3. 任务架构（无 ISR、全任务轮询、单核 C3）

| 任务 | 优先级 | 栈 | 周期 | 职责 |
|---|---|---|---|---|
| Motor_SendTask | 5 | 2048 | 2ms | 算 6 电机电压并发 0x100/0x200 帧 |
| CAN_RecvTask | 5 | 2048 | 2ms | 批量收 CAN 反馈 |
| IMU_Task | 5 | 2048 | 5ms（200Hz） | DMP 取姿态 |
| ADC_Task | 5 | 4096 | 100ms | 电池电压 |
| Ctrl_TargetUpdateTask | 3 | 4096 | 4ms | 目标斜坡与限幅 |
| LegPos_UpdateTask | 2 | 4096 | 4ms | 五连杆腿部解算 |
| Ctrl_Task | 1 | 4096 | **4ms=250Hz 主控环** | LQR+VMC+保护 |
| Serial/BT_SendSample/StandupPrepare | 1 | 4096 | 50/100ms/一次 | 调试/采样回传/起立准备 |

教训：`esp_task_wdt.h` 只 include 从未注册（main.cpp:18）——**"包含头文件 ≠ 开了看门狗"**；电机类工程必须显式 `esp_task_wdt_add()`。另注意上电 `vTaskDelay(5000)` 黑窗（见坑 #81）。

## 4. TWAI（CAN）最小闭环与协议

**初始化**（main.cpp:293-313）：

```c
twai_general_config_t twai_conf = {
    .mode = TWAI_MODE_NORMAL,
    .tx_io = GPIO_NUM_6, .rx_io = GPIO_NUM_7,
    .tx_queue_len = 5, .rx_queue_len = 10,
    .alerts_enabled = TWAI_ALERT_NONE,          // 坑：应含 TWAI_ALERT_BUS_OFF
    .intr_flags = ESP_INTR_FLAG_LEVEL1,
};
twai_timing_config_t twai_timing = TWAI_TIMING_CONFIG_1MBITS();
twai_filter_config_t twai_filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();  // 单过滤器全收
twai_driver_install(&twai_conf, &twai_timing, &twai_filter);
twai_start();
```

**收发模式**：接收任务先 `twai_get_status_info()` 取 `msgs_to_rx` 计数再循环 `twai_receive(&msg, 0)` 批量取走（不逐帧阻塞等待）；发送 `twai_transmit(&msg, 100)`（阻塞上限 100ms，控制环内必须有界）。**必补**：周期查 `TWAI_ALERT_BUS_OFF`，触发后 `twai_initiate_recovery()` + `twai_start()`，否则总线异常后节点永久静默（坑 #72）。

**应用层协议**（控制模式=电压环，非电流环）：

| 方向 | ID | 载荷 | 单位/格式 |
|---|---|---|---|
| 下行 500Hz | 0x100 | 左[关节0,关节1,车轮] 各 int16 | mV（voltage×1000），大端 |
| 下行 500Hz | 0x200 | 右[关节0,关节1,车轮] | 同上 |
| 上行 500Hz | motorID+0x100 | data[0..3]=int32 角度，data[4..5]=int16 转速 | mrad（rad×1000）/ rpm×10 |

ESP32 侧解析：`angle=(raw/1000-offset)*dir`、`speed=(raw/10*2π/60)*dir`（每电机零位 offset 与方向 dir 出厂标定存 STM32）。电机 ID：0x101/102/103=左关节/左轮、0x105/106/107=右、0x104 预留。STM32 bxCAN 1Mbps（Prescaler=2, BS1=11TQ, BS2=4TQ @APB1 32MHz，采样点 75%）、AutoBusOff/AutoRetransmission ENABLE。

**安全兜底分层**（值得照抄）：目标斜坡限幅（速度 ±腿长自适应 / 目标夹在当前 ±0.3m/s、位置 ±0.1m）→ 状态夹紧 → 下位机 500ms 无帧清零输出。上层飞了下层能停。

## 5. IMU 链路（MPU6050 DMP）

- `Wire.begin(5, 4)`（SDA=5/SCL=4，C3）+ `Wire.setClock(400000)`；库 electroniccats/MPU6050 0.6.0 + MotionApps20 DMP。
- 姿态：`dmpGetQuaternion → dmpGetGravity → dmpGetYawPitchRoll`（DMP 硬件融合，无互补/卡尔曼）；yaw 取负、±π 跨越累计整圈。
- 量程：加计显式 `MPU6050_ACCEL_FS_16`，zAccel=dmpGetLinearAccel 后 /8192×9.8；角速度按 16.4 LSB/(°/s)（±2000dps）换算——**但代码未调 setFullScaleGyroRange**，依赖库默认（坑 #75：换算系数必须与实际量程档一致）。
- 零偏：6 个 int 硬编码（accel −668/−1632/998，gyro 283/80/42），标定函数被注释（坑 #73：每块板都要手改；正确做法=上电静止自校准 + NVS 存储）。
- DMP FIFO 速率未显式设置（库默认），轮询 5ms=200Hz 恰为 DMP 上限。

## 6. LQR + VMC 控制律（可复用的部署流）

**状态向量**：`float x[6] = {theta, dTheta, x, dx, phi, dPhi}`（theta=腿角−π/2−pitch 机身折算、x=两轮平均角×R(0.026m)、phi=机身 pitch）。

**K 的离线生成→在线实时计算**（matlab\sys_calc.m → 运行时）：
1. 拉格朗日力学符号推导连续状态空间；
2. `c2d(0.005)` 离散化 → `dlqr(Q=diag([1 10 100 20 1000 1]), R=diag([1 1]))`；
3. 对腿长 L0=0.04:0.01:0.14 逐点求 K，每元素 `polyfit` 三次多项式；
4. MATLAB Coder 生成 `lqr_k(legLength, kRes)` C 函数；
5. 运行时按实测腿长实时算 `K[2][6]`——**非查表非硬编码**，增益随构型连续变化。任何变工况系统（腿长/负载/温度）都适合这条流。

**VMC 虚拟模型控制**：五连杆腿（l1=0.05, l2=l3=0.105, l4=0.05, l5=0.06）；`leg_pos` 由关节角闭环几何解腿长 l0/腿角 φ0；`leg_spd = J·[dφ1; dφ4]`；`leg_conv` 把期望虚拟腿力 F/虚拟髋矩 Tp 经 **雅可比转置** `[T1;T2] = J'·[F;Tp]` 映射为关节扭矩（leg_func_calc.m:35-48）。

**输出合成**：LQR 两输出——轮扭矩（叠加 yawPID 差动）与虚拟髋扭矩（叠加左右腿角差 PID×腿长系数）；扭矩→电压 `voltage = torque/torqueRatio + 反EMF 三次多项式补偿`（torqueRatio 关节≈0.03、轮≈0.01 Nm/V；关节限幅 7V、轮 4V）。

**触地检测**：支撑力 = legLengthPID.output + legMass×9.8 − legMass×(ddLength − zAccel) > 3N，配 1s 防弹跳；离地时手工改写 K 仅保腿竖直、轮扭矩清零。

**安全状态机**：起立三态 None/Prepare/Standup（先摆劈叉再撑起）；`PROTECT_CONDITION` = 任一腿 θ 或机身 pitch 超 ±π/4 → 全电机零扭矩 + 阻塞等待回安全区 + 4s（注意坑 #76：阻塞等待无超时且无 TWDT，IMU/CAN 停更会死等）。

## 7. BLE 遥控与配网（Bluedroid GATT）

- 服务 `4c9a0001-fb2e-432e-92ec-c6f5316b4689`；RX 特征 `4c9a0002`=WRITE_NR（无响应写，高频指令用），TX `4c9a0003`=NOTIFY+BLE2902；设备名 "BalanceBot"。
- 定长帧协议（10Hz 心跳式）：`0xAA len4 [0xAA, yawCh, spdCh, legCh]`，字节=(摇杆值+1)×100（100=中点）；解析 `speedCmd=(d[2]/100−1)×1.0m/s`、`yawSpeedCmd=−(d[1]/100−1)×1.5rad/s`、`legLength=d[3]/200×0.02+0.07`；`0xAB`=起立；`0xAC`=采样回传（10Hz CSV notify）；`0xDB`=Linkscope 调试帧（可读写 RAM——坑 #80：无鉴权无加密，量产必须关）。
- APP 侧：断连 1s 重连、按名扫描+MAC 缓存、请求 PHY_LE_2M。**ESP32 侧无断连超时**（坑 #73）——断连后保持最后指令行驶，靠 STM32 总线超时兜底是错误分层的例子。
- 图传模式进阶：APP 先经 NanoPI BLE（UUID 4c9a0011/12/13）发文本 `SCAN_WIFI`/`CONN_WIFI: ssid\tpasswd`/`GET_IP` 配网，之后改走 UDP :5000 发同款 0xAA 帧、NanoPI 代理写入 ESP32（断流 5s 退回配网态）——"BLE 配网 + UDP 遥控"两级链路模板。

## 8. 与 skill 纪律对照（负例教训）

| 源工程做法 | 违反的纪律 | 正确姿势 |
|---|---|---|
| motor.angle/speed、imuData 跨任务读写无锁 | 硬约束「共享数据 volatile+临界区」 | portMUX 快照或序列锁（坑 #77） |
| 保护分支 while 无超时 | 硬约束「等待必须带超时」 | 有界等待 + TWDT（坑 #76） |
| include esp_task_wdt.h 但从不注册 | 自检「看门狗策略明确」 | esp_task_wdt_add + 喂狗设计 |
| 零偏/整定参数全硬编码 | 「参数可标定」 | 静止自校准 + NVS 存储 |
| 电池 <8V 置假值 12 | 「异常就地处理」 | 低压直接停机（坑 #78） |

## 9. 可复用模式清单

1. TWAI 最小闭环（install 1Mbps 全收 filter → start → 状态查询批量收 → 发送带超时）+ bus-off 恢复补丁。
2. Arduino-as-IDF-component 混编（app_main→setup/loop 桥）。
3. MATLAB 离线 LQR 部署流（符号建模→dlqr→K(工况) 多项式拟合→Coder 生成→运行时实时算 K）。
4. VMC 雅可比转置力映射 `[T]=J'·[F;Tp]`。
5. 串级 PID 通用模板（内外环、积分/输出双限幅、误差低通、死区——PID.h）。
6. 定长帧 BLE 遥控（WRITE_NR 收 + NOTIFY 回 + 10Hz 心跳 + 指令超时清零）。
7. 分级失控保护（斜坡限幅→状态夹紧→下位机总线超时）。
8. 单按键时长复用 UI（1 短按设 yaw 基准/2 起立/3 前进 2s/4 前进 5s/5 转 180°）。
9. 「BLE 配网 + UDP 遥控」两级链路。

## 10. 坑位索引

本文相关坑位见 [known-pitfalls.md](known-pitfalls.md)「电机控制类」#72–#81：CAN bus-off 静默、BLE 断连沿最后指令行驶、零偏硬编码、陀螺量程档不符、保护死等无看门狗、跨任务无锁、低压假值、端到端延迟叠加、调试帧可写 RAM、上电 5s 黑窗。
