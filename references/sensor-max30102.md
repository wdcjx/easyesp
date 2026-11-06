# MAX30102 心率血氧传感器实战配方

> 何时读：用 MAX30102（或 MAX30101/03）做心率 / 血氧 / 脉搏波采集时——初始化寄存器序列、FIFO 读取、心率血氧算法、手指在位检测、坑位速查。
> 状态：实战项目沉淀（源自已上板工程 `D:\ESP32project\xiaozhi-esp32-main\heart-rate-spo2-master`，Arduino + MicroPython + PC 三版；本文为源码转写，未在本机二次复测；寄存器语义与供电参数以 MAX30102 datasheet 为准）。

源码锚点约定（相对 `heart-rate-spo2-master\HeartRate_SPO2\`）：INO=`HeartRate_SPO2_arduino\HeartRate_SPO2_arduino.ino`（依赖外部 SparkFun_MAX3010x 库）；MPY=`HeartRate_SPO2_micropython`（`main.py` + `lib\max30102\__init__.py`，下称 init.py）；PC=`HeartRate_SPO2_PC`（`Max_30102.py` 串口解析 + 算法）。

## 1. 硬件与接线

| 项 | 值 | 出处 |
|---|---|---|
| 传感器 | MAX30102 反射式心率血氧模块 | README.md:7 |
| I2C 地址 | 7bit `0x57`（8bit 0xAE/0xAF 右移而来） | init.py:24 |
| ESP32 + Arduino IDE | SDA=IO8、SCL=IO9（README 给的是 C3 接法；INO 未显式 `Wire.begin(sda,scl)`，用板卡默认引脚：经典 esp32=21/22，C3=8/9） | README.md:39、INO |
| ESP32 + MicroPython | SoftI2C SDA=IO10、SCL=IO6，400kHz | mp main.py:5-11 |
| 其他板参考 | Pico IO4/IO5、Nano/Uno A4/A5、STM32 B7/B6 | README.md:31-43 |
| 供电 | 仓库未写明；ESP32 侧 3.3V 逻辑，VLED 电压 / 模块自带上拉以模块原理图为准 | — |
| LED 电流 | 亮度参数 150 ≈ 29mA（0=Off..255=50mA 线性） | INO:18 |

物理注意（README.md:79-80）：手指按压易碰到外围电路，用胶带隔离感光区；**反射式精度低于透射式医疗设备**、读数受按压力度影响，结果仅供参考不作临床依据。

## 2. 初始化寄存器序列（MPY 版逐条，寄存器级完整实现）

init.py `setup_sensor()`（init.py:187-219），`main.py` 传 `led_power=150、sample_rate=400`，其余默认（led_mode=2 / adc_range=16384 / sample_avg=8 / pulse_width=411µs）：

| 步 | 寄存器 | 值 | 含义 | 锚点 |
|---|---|---|---|---|
| 1 | MODE_CONFIG `0x09` | 0x40 | RESET 位，轮询等自清 | init.py:278-287 |
| 2 | FIFO_CONFIG `0x08` | 0x60 | SMP_AVE=8 样本平均 | init.py:429-444 |
| 3 | FIFO_CONFIG `0x08` | 0x10 | ROLLOVER=1（FIFO 满后循环覆盖） | init.py:471-473 |
| 4 | MODE_CONFIG `0x09` | 0x03 | MODE=SpO2（Red+IR 双 LED） | init.py:307-308 |
| 5 | MULTI_LED_CONFIG1 `0x11` | slot1=0x01 / slot2=0x20（`0x21` 合成） | 双通道时隙 | init.py:316-318,544-551 |
| 6 | SPO2_CONFIG `0x0A` | 0x60 | ADC_RGE=16384nA | init.py:332-343 |
| 7 | SPO2_CONFIG `0x0A` | 0x0C | SR=400sps | init.py:353-372 |
| 8 | SPO2_CONFIG `0x0A` | 0x03 | LED_PW=411µs / 18bit ADC | init.py:383-393 |
| 9 | LED1PA `0x0C` / LED2PA `0x0D` / LED3PA `0x0E` / PROX `0x10` | 150 (0x96) | 各通道电流 | init.py:213-216 |
| 10 | FIFO_WR `0x04` / OVF `0x05` / RD `0x06` | 清 0 | 复位 FIFO 指针 | init.py:464-469 |

合成结果：`0x08=0x70`、`0x09=0x03`、`0x0A=0x6F`；**有效输出率 = 400/8 = 50Hz**（init.py:450-459）。

> 注意：init.py:42-43 注释把 0x0C 标 IR、0x0D 标 RED，**与 datasheet 相反**（以 MAX30102 datasheet 为准：0x0C=Red、0x0D=IR）；代码按地址写入且两通道同幅值，无功能影响，但读注释会误导。

Arduino 版寄存器写入全在 SparkFun_MAX3010x 库内（仓库未内嵌源码，逐条以 SparkFun 库源码为准），INO 只做：`begin(Wire, I2C_SPEED_FAST)`=400kHz（INO:11）+ `setup(ledBrightness=150, sampleAverage=4, ledMode=2, sampleRate=200, pulseWidth=411, adcRange=16384)`（INO:18-25）→ 有效 200/4=50Hz，与 MPY 节拍一致。INO:3 引入了 spo2_algorithm.h 但全文未调用任何算法函数（纯采集透传）。

## 3. FIFO 读取与样本格式

| 项 | 事实 | 锚点 |
|---|---|---|
| 指针寄存器 | FIFO_WR=0x04、OVF=0x05、FIFO_RD=0x06、FIFO_DATA=0x07 | init.py:33-36 |
| 样本计数 | n = WR−RD，为负则 +32（32 深硬件 FIFO） | init.py:650-660 |
| MPY 读取节奏 | `check()` 每次只读 **1 个样本**（for 体内 return True） | init.py:662-684 |
| 溢出处理 | OVF 从不读取 + rollover 已开 → 溢出**静默覆盖旧样** | init.py:471-473 |
| 样本长度 | 每 LED 3 字节，mode2 每样本 6B = active_leds×3 | init.py:322-325,663-665 |
| 字节序 | 大端 18bit：`(unpack(">i", b'\x00'+b)[0] & 0x3FFFF) >> self._pulse_width`，`_pulse_width` 存寄存器值 pw∈0..3 → 411µs 时右移 3 | init.py:581-583,396 |
| 通道顺序 | 字节 [0:3]→Red、[3:6]→IR | init.py:669-677 |
| 软件 FIFO | deque maxlen=4（满丢旧）；circular_buffer.py 的 pop_head 实现有 bug 但 main.py 未用 | init.py:156、circular_buffer.py:16-41 |
| 输出帧 | `[DATA] red=XXX,ir=XXX,time=XXX`（time 单位 ms，red 在前） | README.md:49-54、INO:34-42 |

**量纲陷阱**：MPY 版 `>>pulse_width`（=3）使数值 ÷8，SparkFun 库 18bit 原始值不移位 → 两固件的 red/ir 数值差 8 倍，阈值必须按固件区分（见 known-pitfalls #54）。

Arduino 侧经 SparkFun `available()/check()/nextSample()/getRed()/getIR()`（INO:30-39）。

## 4. 心率算法（PC 版 Max_30102.py）

| 环节 | 实现 | 锚点 |
|---|---|---|
| 滤波（仅显示） | `butter(8,0.1,"highpass")` + `butter(8,0.3,"lowpass")` + filtfilt + detrend；Wn 是相对 Nyquist 的归一化频率 | Max_30102.py:28-29,126-159 |
| 找峰 | **pyampd `find_peaks`=AMPD 自动多尺度峰值查找，作用于未滤波 red 序列** | Max_30102.py:5,72 |
| BPM | `60000/(time[peaks[-2]]−time[peaks[-3]])`，单个 RR 间期折算；需 len(peaks)>3，异常返回 0 | Max_30102.py:74-82 |
| 显示平滑 | 最近 10 次均值、每 1s 刷新（avg_rate=10） | Max_30102.py:14,87-116 |

## 5. SpO2 算法（Max_30102.py:56-67）

```python
DC = min(窗口); AC = max(窗口) - min(窗口)          # 假设窗内含完整搏动、基线=最小值
R2 = (red_ac * ir_dc) / (red_dc * ir_ac)           # ≡ (AC/DC)_red ÷ (AC/DC)_ir
SPO2 = -45.060*R2**2 + 30.354*R2 + 94.845          # 经验二次曲线
# >100 或 <0 时整体置 0（判无效）
```

README 无与标准血氧仪的偏差数据，仅声明反射式、仅供参考（README.md:80）。

## 6. 手指在位 / 信号质量判据

- 指位：唯一判据 `ir > 150000` → Fin=1（基于 **SparkFun 18bit 量纲** 的经验值；MPY 固件数值÷8 后该阈值失效，见 #54）。锚点 Max_30102.py:172-175。
- data_valid：三缓冲均 ≥ Samplerate（=120）样本才开始计算。锚点 Max_30102.py:91-96。

## 7. 三版对照

| 维度 | Arduino INO | MicroPython | PC |
|---|---|---|---|
| 驱动 | 外部 SparkFun 库 | 仓库内寄存器级 init.py | 无，串口解析 |
| I2C / 口 | Wire 400kHz | SoftI2C(SDA10,SCL6) 400k | 115200 自动取第一个串口 |
| 配置 | 150/4/2/200/411/16384→50Hz | 150/8/2/400/411/16384→50Hz | 窗口 Samplerate=120 样本 |
| 原始值量纲 | SparkFun 18bit 不移位 | >>pw=3 → 差 8 倍 | — |
| 算法 | 无，透传 | 无，透传 | AMPD 心率 + 二次曲线 SpO2 + 指位 |
| 输出 | UART `[DATA]` | REPL print `[DATA]` | DearPyGui GUI + socket 0.0.0.0:9999 JSON 每 50ms |

## 8. 坑位索引（详见 known-pitfalls.md）

#54 指位恒失效（量纲 ÷8）｜#55 I2C 无 ACK｜#56 丢样（单样本读+OVF 不读+队列 4 深）｜#57 BPM 跳变（未滤波找峰+单 RR）｜#58 SpO2 跳 0｜#59 改采样率后全乱（隐含 50Hz）｜#60 通道接反 / 注释红反｜#61 供电与 LED 峰值电流
