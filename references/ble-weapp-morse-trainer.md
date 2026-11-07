# BLE + 微信小程序外设实战：莫尔斯电码练习器（cw_esp32_ble_weapp）

> 何时读：要做「ESP32 ↔ 手机小程序」BLE 外设、BLE GATT 服务端单特征命令管道、touchRead 触摸输入、蜂鸣器 CW 时序控制、或评估 2020 年代 Arduino-ESP32 老项目向 core 3.x 迁移时。
> 状态：实战转写（源工程 github.com/chenqingspring? 见 README「ZClubCola」，作者已上板运行多年，v0.0.3 / 2020-12；API 为 arduino-esp32 1.0.x 时代 Bluedroid + 经典 ledc，本文已逐条标注 core 3.x 漂移；未在本会话复测）。源码 12 文件全读，含 5 处实证 bug。

## 1. 系统定位与架构

莫尔斯电码（CW）练习器：ESP32 经典板做 BLE GATT 服务端，微信小程序「ZClubCola」（闭源，未随仓库发布）做界面与 MQTT 中继——**ESP32 侧无任何 WiFi/MQTT 代码**，联网职责全部在手机端。这是「瘦设备 + 胖网关」分层的教科书样本：固件只管按键采集、本地蜂鸣、电码缓冲，云端呼号广播由小程序完成。

| 文件 | 职责 | 关键点 |
|---|---|---|
| cw_esp32_ble_weapp.ino | setup/loop | ledc 蜂鸣、按 s_key_type 分发电键检查 |
| ble.h | GATT 服务端 | Bluedroid（BLEDevice.h），单特征 4 属性 |
| op_code.h | 播放/空格/自动发送 | 两次空格状态机、阻塞 delay 播放 |
| auto_key.h / manual_key.h | 双桨自动键 / 手动键 | 自捶节奏、地狱模式容错窗 |
| op_settings.h / op_eeprom.h | 14 项参数收发与持久化 | 定长 5 字符记录 + magic 首启 |
| var_settings.h / var_morse.h / pin.h / op_bee.h / time_tools.h | 全局状态/码表/引脚/蜂鸣/计时 | 全局可变共享状态 |

数据流：电键→loop 轮询→`ble_send("code","."|"-"|" "|"*")` notify 小程序；小程序→onWrite→`set:key:val`（参数）/`ply:码`（本设备同步播放）/`plc:码`（另核异步播放）/`stp`（停）。

## 2. 微信小程序 BLE 对接事实

小程序端不随仓库发布，以下为 ESP32 侧协议反推 + 微信官方 API 通用事实（以官方文档为准）：

- 小程序蓝牙链路：`wx.openBluetoothAdapter` → `wx.startBluetoothDevicesDiscovery({services:[SERVICE_UUID]})` → `wx.createBLEConnection` → `wx.getBLEDeviceServices/Characteristics` → `wx.notifyBLECharacteristicValueChange`（订阅 NOTIFY）→ `wx.onBLECharacteristicValueChange` 收 / `wx.writeBLECharacteristicValue` 发。README「点击状态图标即搜索」正对应这条链。
- **Android deviceId = MAC 地址；iOS 无 MAC 概念，deviceId 为系统随机 UUID**——重连逻辑两端必须分别处理（源工程靠「搜索→用户手点设备列表」回避了持久化重连）。
- iOS 需在 app.json 声明蓝牙用途权限；微信基础库低版本曾要求 Android 定位权限才能扫描 BLE（历史坑，新基础库已放宽）。
- 广播包带 SERVICE_UUID + setScanResponse(true)，小程序才能按 services 过滤发现设备。
- MTU：Bluedroid 默认 ATT MTU 23 → 单帧 notify 载荷 ≈20B。本协议帧极短（"inp:-"4B）无压力；设计新协议时不可超。

## 3. GATT 单特征文本协议（实证含越界 bug）

| 项 | 值 |
|---|---|
| SERVICE_UUID | `6880d7e7-93ba-4fdf-8940-31226ab93ac6` |
| CHARACTERISTIC_UUID | `ccc5dfd0-6ce3-4f1a-9ab9-f7d9a88321ec` |
| 特征属性 | READ \| WRITE \| NOTIFY \| INDICATE 四合一 |
| 帧 | 冒号分割文本 `set:key:val` / `ply:码` / `plc:码` / `stp`；上行前缀 `inp:`（电码流）/`cmd:`（命令回执，如 `cmd:send`/`cmd:play_done`） |

单特征多路复用的取舍：小程序端一次订阅拿全部消息，零协商成本，适合参数面板类外设；代价是无帧界/无转义/无版本号。**实证 bug**：`ble_op_msg` 分割器 `p++` 无上限、`info[p] += msg[i]`——`info` 只有 3 格，收到含 ≥3 个冒号的帧即越界写栈（正常客户端不会发，但固件侧无防御；写外设协议必须假定对端可被伪造）。

## 4. Bluedroid 服务端骨架与断连缺陷

最小可用骨架（源码同构，可直接套）：

```cpp
#include <BLEDevice.h>
#include <BLEServer.h>
BLECharacteristic *pCharacteristic;           // 全局指针，回调与 loop 共用
class Cb : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override { /* 入参校验后转发解析 */ }
};
void ble_init() {
  BLEDevice::init("ZClub CW");
  BLEServer *srv = BLEDevice::createServer();
  BLEService *svc = srv->createService(SERVICE_UUID);
  pCharacteristic = svc->createCharacteristic(CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE |
      BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_INDICATE);
  pCharacteristic->setCallbacks(new Cb());
  pCharacteristic->addDescriptor(new BLE2902());   // CCCD：NOTIFY 必需，源工程由库隐式补
  svc->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}
```

**源工程最大缺陷：无 `BLEServerCallbacks::onDisconnect` 回调，断连后不重启广播**——手机一旦断开（超出范围/小程序杀后台），设备从此不可发现，只能断电重启。修复模式（所有 BLE 外设通用）：

```cpp
class SrvCb : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override { deviceConnected = true; }
  void onDisconnect(BLEServer *s) override {
    deviceConnected = false;
    BLEDevice::startAdvertising();          // 断连即重新广播，否则永久失联
  }
};
srv->setCallbacks(new SrvCb());
```

发送侧：`setValue((uint8_t*)str, len)` + `notify()`；notify 在客户端未写 CCCD 时静默丢弃，发送前应判 `deviceConnected`。`setMinPreferred(0x06)` 后紧跟 `setMinPreferred(0x12)` 是从官方示例抄来的双行（后者覆盖前者，单位 1.25ms 连接间隔，注释"iPhone 兼容"仅具参考意义）。

## 5. CW 时序体系（本工程核心领域知识）

参数默认值（var_settings.h，全可经 BLE 修改并落盘）：

| 参数 | 默认 | 语义 |
|---|---|---|
| s_u_time | 50ms | 点长（自动键自捶单位、手动键点/划分界） |
| s_di_da_scale | 3.0 | 划/点比例（标准 3） |
| s_shake_time | 30ms | 按压防抖下限（小于视为无效） |
| s_play_u_time | 120ms | 播放单位（与录入解耦：可慢发快收） |
| s_auto_send_time | 2000ms | 空闲多久自动 `cmd:send` |
| s_split_time | 300ms | 字母间隔语义参数 |
| s_touch_val | 20 | touchRead 触发阈值（小于即按下） |
| s_fault_rate | 0.10 | 地狱模式容错百分比窗 |

- **手动键**：沿检测（flag_rcd 记按压沿），释放时 diff_time<s_u_time 为点、否则为划；地狱模式改为容错窗 `u*(1±r)` 与 `3u*(1±r)`，窗外发 `*` 无效字符（判分语义）。容错 0% 时窗口坍缩为精确毫秒命中（README 自嘲"祝你玩得开心"）。
- **自动键（双桨）**：按住即 `bee+delay(s_u_time)` 自捶，无 iambic 记忆——`delay` 阻塞 loop 使两桨互不可感知，松一桨换一桨的交替节奏由 loop 轮询自然形成 `. - . -`。
- **两次空格状态机**（check_space）：键入后 flag_space=true；空闲 >2×s_u_time 发第一个空格（字母界）；再空闲一个周期发第二个空格并置 flag_send=true（词界+武装发送）；再过 s_auto_send_time 发 `cmd:send` 通知小程序上传 MQTT。cs_time 一个变量同时充当防抖计时、按压时长测量、空格间隔测量三职。
- **播放**：`play_code` 逐字符阻塞 `delay`；`plc` 命令走 `play_code_core` 把整串码 pin 到核 1 的独立任务逐字符播放，`stp` 置 flag_play_code=false 使其自杀。**实证 bug**：空格分支 `if(s_split_time*3 < 80) delay(80); else delay(sp_time*3);`——条件用 s_split_time、延时却用 sp_time（=s_play_u_time），s_split_time 对播放路径完全失效，属变量错位。

## 6. 触摸电键与 touchRead

- 经典 ESP32 专属：T0–T9 对应 GPIO0/2/4/12/13/14/15/27/32/33（本工程用 T8=GPIO33、T9=GPIO32 做双触摸桨），触摸时读值**下降**，阈值判 `< s_touch_val`。
- 源码注释实证：未触摸时偶发读 0（原因待查）→ 防御式二次读 `if(v==0) v=touchRead(pin);`。0 会误触"按下"，必须滤。
- **S3 / C3 没有触摸外设**：此机制无法移植，换 GPIO 按键或电容芯片（如 TTP223）。
- arduino-esp32 1.0.x 的 touchRead 返回原始计数值；2.x 起改为经校准的近似值，同一阈值跨版本不可比（以官方迁移说明为准）。

## 7. 引脚分配与 strapping 教训

| 信号 | 引脚 | 隐患 |
|---|---|---|
| 自动键 di 桩 | GPIO0 | **BOOT strapping**：按住上电/复位进下载模式，烧录失败；生产不可用 |
| 手动键/自动键 da 桩 | GPIO4 | 手动模式 `pinMode(pin_key, INPUT_PULLUP)` 被注释，GPIO4 的上拉是自动键初始化的副作用——两键改不同引脚后手动键悬空乱触发 |
| 蜂鸣器 | GPIO23 | 高电平触发，ledcWriteTone 驱动，无源蜂鸣器 |
| 触摸桨 | GPIO33/32 | 经典 ESP32 专属，见 §6 |

## 8. 设置持久化：EEPROM 定长记录范式（与正道对照）

Arduino-ESP32 的 `EEPROM.h` 是 NVS 上的模拟层（`EEPROM.begin(size)` 映射 NVS 命名空间，`commit()` 全量写）。源工程范式：14 项设置各占 5 字符定长右对齐零填充（"1800"→"01800"），尾部再存作者呼号 "BG7YXY" 当 magic 判断首启。**每改一项参数即 `EEPROM.write×5 + commit` 一次**——设置面板连点就是连次 NVS 整块擦写。float 落盘走 `String(3.0)="3.00"`（两位小数恰好 4 字符，纯属参数范围运气）。正道：`Preferences`（NVS 原生，键值级磨损均衡、类型安全），同一数据一行 `prefs.putInt("u_time", 50)`；EEPROM 模拟层仅为 AVR 迁移兼容存在。定长记录+magic 首启的**思想**可取（版本化配置区+出厂默认回填），载体应换 NVS。

## 9. 迁移与现代化（若今日重建）

- core 3.x 弃用线：`ledcSetup/ledcAttachPin/ledcWriteTone`（通道制）→ `ledcAttach(pin, freq, res)` + `ledcWriteTone(pin, freq)`（引脚制）；源码三处全在弃用区。
- Bluedroid（BLEDevice.h，约 400KB+ 协议栈）→ **NimBLE-Arduino**（省 ~500KB flash/100KB+ RAM，API 同构度 80%+），回调签名改 `NimBLECharacteristicCallbacks`；本 skill 的 BLE HID 配方（ble-hid-keyboard.md）已给 NimBLE 全样。
- 阻塞 delay 自捶 → `esp_timer`/gptimer 周期回调 + 状态机；iambic 记忆需事件化按键采集。
- 单特征文本协议 → 若消息类别增多：特征分路（参数/电码流/回执各一）或首字节类型码+长度，替代裸冒号分割并加越界防护。

## 10. 纪律对照（与 SKILL.md 硬约束的映射）

- 违反「ISR/回调内不做长活」：onWrite 回调内 `ply` 直接阻塞播放数秒（坑 126）。
- 违反「先探测再引用」：手动键 GPIO4 上拉依赖另一模块的初始化副作用（坑 127）。
- 违反「strapping 引脚不接按键」：GPIO0 做 di 桩（坑 128）。
- 违反「共享状态需护」：var_ble_msg/var_code_list 全局 String 跨任务无锁（坑 130）。
- 违反「持久化按需写入」：每参数一次 NVS 全量 commit（坑 132）。

## 11. 可复用模式

1. 瘦设备+胖网关：BLE 外设不碰 WiFi/MQTT，手机小程序代持云端身份——固件零密钥、零配网。
2. 单特征四属性命令管道：参数面板类外设的最简 GATT 拓扑（需加帧界与越界防护再用于生产）。
3. 录入/播放双时钟：s_u_time（手速）与 s_play_u_time（播速）解耦，抄报训练可慢发快放。
4. 容错窗判分：`中心值×(1±容错率)` 双侧窗替代单阈值分界，窗外语义显式化为 `*` 无效字符。
5. 定长记录+magic 首启：配置区版本化与出厂默认回填（载体改 NVS/Preferences）。
6. 触摸读 0 防御：异常极值二次读，适用于一切慢变模拟量轮询。
7. 断连即重广播：BLE 服务端 onDisconnect → startAdvertising，可发现性自愈。

## 12. 坑位索引（125–138，详见 known-pitfalls.md）

125 断连不重启广播永久失联 / 126 onWrite 内阻塞播放卡 BLE 栈 / 127 手动键上拉靠自动键副作用 / 128 GPIO0 strapping 做按键 / 129 touchRead 偶发 0（二次读防御；S3/C3 无触摸）/ 130 共享全局 String 跨任务无锁 / 131 ble_send 声明与定义签名漂移 / 132 每参数一次 EEPROM 全量 commit / 133 定长 5 字符零填充存储截断与 float 运气 / 134 play_code 空格分支变量错位（s_split_time 失效）/ 135 冒号分割器越界写栈 / 136 自捶 delay 阻塞无 iambic / 137 setMinPreferred 连调后者覆盖 / 138 39 个 String 码表常驻堆+频繁拼接碎片。
