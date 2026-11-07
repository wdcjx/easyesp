> 何时读：需要创建/修改/编译/烧录 ESP-IDF 工程，或查错误处理、日志、组件、menuconfig、分区表、sdkconfig 纪律
> 状态：知识沉淀（未上板实测；API 对齐 ESP-IDF 5.3.x / arduino-esp32 3.x 官方文档）

# ESP-IDF 工程解剖与构建闭环

## 1. 工程目录树

| 路径 | 职责 |
|---|---|
| CMakeLists.txt | 根构建脚本，三行固定（见下），不可省略 |
| main/CMakeLists.txt | 组件注册：SRCS / INCLUDE_DIRS / REQUIRES |
| main/main.c | 入口，定义 `void app_main(void)`（不是 main） |
| sdkconfig | menuconfig 生成的全量生效配置；禁止手改、禁止提交 |
| sdkconfig.defaults | 配置默认值差异；仓库唯一提交的配置件 |
| partitions.csv | 自定义分区表，Partition Table=Custom 时生效 |
| main/idf_component.yml | 组件管理器依赖声明 |
| managed_components/ | 自动拉取的第三方组件，禁止手改 |
| build/ | 产物：.elf / .bin / .map / bootloader / 分区表 |

根 CMakeLists.txt（最小可编译，三行固定）：
```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(my_app)
```

main/CMakeLists.txt：
```cmake
idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS ".")
```

main/main.c 最小骨架：
```c
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "app";

void app_main(void)                        /* IDF 入口；app_main 运行于一个任务内 */
{
    ESP_LOGI(TAG, "hello");
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));   /* 阻塞等待，让出 CPU */
    }
}
```

## 2. 构建闭环命令表（在工程根目录执行）

| 命令 | 作用 / 要点 |
|---|---|
| `idf.py set-target esp32` | 或 esp32s3 / esp32c3；换目标必须重跑（自动清 sdkconfig 与 build 配置；构建仍异常则手动 fullclean） |
| `idf.py menuconfig` | 交互配置，`/` 搜索，S 保存退出；结果写 sdkconfig |
| `idf.py build` | 增量构建，产物在 build/ |
| `idf.py -p COMx -b 460800 flash` | 烧录；失败可把 -b 降到 115200 |
| `idf.py -p COMx monitor` | 串口监视器，退出按 Ctrl+]；可连写 `idf.py -p COMx flash monitor` |
| `idf.py fullclean` | 整体删 build/；必跑场景：换 target 残留、sdkconfig 冲突残留、构建行为诡异 |
| `idf.py size` / `size-components` | 总 Flash/RAM 占用 / 按组件拆分 |
| `idf.py partition-table` | 打印实际烧录的分区表 |
| `idf.py reconfigure` | 仅重跑 CMake（依赖变更后刷新） |

## 3. 本机环境探测（写代码前先确认）

- ESP-IDF 安装位置不写死：Windows 官方安装器默认 `%USERPROFILE%\esp\`（自定义目录以实际为准）；先探测再引用路径
- 激活：安装目录的 `idf_cmd_init.bat` / `export.ps1`，或开始菜单「ESP-IDF x.x PowerShell」快捷方式；激活后 idf.py 才在 PATH
- Windows 系统 `python` 可能是 Microsoft Store 空壳（报 "No installed Python found!" 或商店弹窗）——跑脚本改用 IDF 自带解释器（`<安装目录>\Espressif\python_env\idf*_env\Scripts\python.exe`，具体目录名含 IDF 版本，先探测）或激活 IDF 后的 python

## 4. 错误处理范式

`#include "esp_err.h"`；ESP_RETURN_ON_ERROR 宏族来自 `#include "esp_check.h"`。

| 符号 | 值 | 含义 |
|---|---|---|
| ESP_OK | 0 | 成功 |
| ESP_FAIL | -1 | 通用失败 |
| ESP_ERR_NO_MEM | 0x101 | 内存不足 |
| ESP_ERR_INVALID_ARG | 0x102 | 参数非法 |
| ESP_ERR_INVALID_STATE | 0x103 | 状态错误 |
| ESP_ERR_NOT_FOUND | 0x105 | 未找到 |
| ESP_ERR_NOT_SUPPORTED | 0x106 | 不支持 |
| ESP_ERR_TIMEOUT | 0x107 | 超时 |

日志中的 0x??? 即上述错误码；`esp_err_to_name(err)` 转可读名。

| 机制 | 行为 / 场景 |
|---|---|
| ESP_ERROR_CHECK(err) | err!=ESP_OK 时 abort（打印位置、表达式、返回值与回溯后重启）；用于不可恢复的初始化 |
| ESP_ERROR_CHECK_WITHOUT_ABORT(err) | 只记日志不 abort，表达式返回值即 err |
| ESP_RETURN_ON_ERROR(err, TAG, fmt, ...) | 失败时记日志并 `return err`；适用于返回 esp_err_t 的函数 |
| ESP_RETURN_ON_FALSE(cond, ret, TAG, fmt, ...) | cond 为假时返回 ret |
| ESP_GOTO_ON_ERROR(err, tag, TAG, fmt, ...) | 失败时置 ret=err 并 `goto tag`；要求函数内已声明名为 `ret` 的 esp_err_t 变量 |

goto cleanup 完整示例：
```c
#include "esp_check.h"
#include "esp_log.h"
#include "nvs_flash.h"

static const char *TAG = "app";

esp_err_t app_init(void)
{
    esp_err_t ret = ESP_OK;               /* ESP_GOTO_ON_ERROR 依赖名为 ret 的变量 */

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_GOTO_ON_ERROR(nvs_flash_erase(), cleanup, TAG, "erase");
        err = nvs_flash_init();
    }
    ESP_GOTO_ON_ERROR(err, cleanup, TAG, "nvs init: %s", esp_err_to_name(err));

    /* ...其他初始化 */
    ESP_LOGI(TAG, "init ok");

cleanup:
    /* 失败路径在此释放已获取资源 */
    return ret;
}
```

## 5. 日志

```c
#include "esp_log.h"
static const char *TAG = "app";   /* 每文件一个 TAG 的约定 */
ESP_LOGE(TAG, "err %d", v);       /* W/I/D/V 同型，printf 风格 */
```
- 编译期：menuconfig → Component config → Log output → Maximum log verbosity（CONFIG_LOG_MAXIMUM_LEVEL），更深的日志不编入固件
- 运行期：`esp_log_level_set("app", ESP_LOG_DEBUG);` 或 `esp_log_level_set("*", ESP_LOG_WARN);`，不能超过编译期上限
- printf 同样输出到 console（默认 UART0），但无 TAG 与级别控制

## 6. 组件模型

```cmake
idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi nvs_flash esp_netif     /* 公有：依赖方也能看到这些头 */
                       PRIV_REQUIRES esp_timer)                  /* 私有：仅本组件源文件使用 */
```
漏声明 → `fatal error: xxx.h: No such file or directory`。常见组件：driver（GPIO/UART/SPI/I2C/LEDC）、esp_wifi、nvs_flash、esp_timer、esp_event、esp_netif、mqtt（头文件 mqtt_client.h）、mdns、app_update（OTA）、spiffs。

第三方依赖写进 main/idf_component.yml：
```yaml
dependencies:
  espressif/led_strip: "^2.5.0"
```
构建时自动拉到 managed_components/；更新用 `idf.py update-dependencies`（或删 managed_components/ 后重建）；禁止手改其内容。

## 7. 关键 menuconfig 项

| 菜单路径（CONFIG） | 要点 |
|---|---|
| Serial flasher config → Flash size（ESPTOOLPY_FLASHSIZE） | 须与板子实际 Flash 一致；经典 esp32 常见 4MB，S3 常见 8MB |
| Partition Table（PARTITION_TABLE_TYPE） | Single factory / Factory+两 OTA / Custom CSV |
| Component config → ESP PSRAM → Support for external, SPI-connected RAM（SPIRAM） | 带 PSRAM 的 S3 板必开 |
| Component config → ESP System Settings → Channel for console output（ESP_CONSOLE_*） | UART0（默认）/ USB Serial/JTAG（S3/C3）/ USB CDC |
| Component config → FreeRTOS → Tick rate（FREERTOS_HZ） | 默认 100Hz，影响 pdMS_TO_TICKS 与定时粒度 |
| Component config → FreeRTOS → Task Watchdog（ESP_TASK_WDT） | 任务不喂狗触发复位，默认超时 5s |

## 8. 分区表

默认布局（以 4MB Flash、Single factory app 为例）：
```
# Name,   Type, SubType, Offset,  Size
nvs,      data, nvs,     0x9000,  0x5000,   /* 键值存储：WiFi 校准/用户数据 */
phy_init, data, phy,     0xe000,  0x1000,   /* RF/PHY 校准数据 */
factory,  app,  factory, 0x10000, 1M,       /* 出厂应用 */
```
Factory+两 OTA 方案增加：otadata（data/ota，记录下次启动哪个 ota_x）+ ota_0/ota_1（A/B 双应用槽，互为升级备份）。0x1000（经典，S3/C3 为 0x0）处是 bootloader，0x8000 处是分区表自身；app 分区偏移须 0x10000 对齐。实际布局以 `idf.py partition-table` 输出为准。

partitions.csv 字段：
| 字段 | 取值 / 约束 |
|---|---|
| Name | 唯一；代码中 esp_partition_find_first(TYPE, SUBTYPE, "name") 定位 |
| Type | app / data |
| SubType | app：factory, ota_0…ota_15, test；data：ota, nvs, nvs_keys, phy, coredump, spiffs, fat, esphttpd |
| Offset | 可留空自动对齐；首个 app 分区惯例 0x10000 |
| Size | 带单位（1M/512K）或十六进制 0x10000 |
| Flags | encrypted 或留空（加密数据分区） |

OTA 双应用分区示例（4MB，menuconfig 选 Custom Partition Table，文件名默认 partitions.csv）：
```
# Name,   Type, SubType, Offset,  Size,     Flags
nvs,      data, nvs,     0x9000,  0x5000,
otadata,  data, ota,     0xe000,  0x2000,
phy_init, data, phy,     0x10000, 0x1000,
ota_0,    app,  ota_0,   0x20000, 0x1F0000,
ota_1,    app,  ota_1,   0x210000,0x1F0000,
```
两个 app 分区都要 ≥ 最大固件尺寸；bootloader 按 otadata 指针选择启动槽。

## 9. sdkconfig 纪律

- 仓库只提交 sdkconfig.defaults，不提交 sdkconfig（全量、依赖目标与环境）
- 禁止手改 sdkconfig：正规入口是 `idf.py menuconfig`，手改会被覆盖
- 改默认值流程：menuconfig 调整 → `idf.py savedefconfig` 导出最小差异 → 把变更行（CONFIG_XXX=value）并入 sdkconfig.defaults
- 改 sdkconfig.defaults 后要删旧 sdkconfig 并 fullclean，否则旧 sdkconfig 优先生效
- 按目标差异化：sdkconfig.defaults.esp32s3 等后缀文件对该目标优先生效
