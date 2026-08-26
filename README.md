# 银河麒麟服务器多架构包下载工具

版本：`1.1.0`

Debian 包名：`kylin-server-rpm-search`

基于 Python + PyQt5，用于浏览、搜索和批量下载银河麒麟、中标麒麟服务器多架构 RPM 软件包。

## 选择流程

```text
产品源 → 系统版本 → 发行版本号 → 系统维护与补丁组件 → 芯片架构 → 软件仓库 → 搜索 → 开始下载 → 下载内容
```

- 产品源：银河麒麟服务器 `NS`、中标麒麟服务器 `CS`。
- 系统版本：`V10`、`V11`；CS 当前仅提供 V10。
- NS V10 发行版：`V10SP1`、`V10SP2`、`V10SP3`、`V10SP3-2403`。
- NS V11 发行版：`2503`、`V11SP1-2603`。
- 系统维护与补丁组件默认为 `os`。
- 默认选择：`NS → V10 → V10SP3 → os → aarch64 → base/update`。
- CS V10SP3 映射实际 `hwy/os`；CS V10SP3-2403 提供 `aiplus/os`、`ccw/os`、`lowlatency/os`、`kernel-4k`。

## 主要功能

- 支持 `aarch64`、`x86_64`、`loongarch64`、`sw_64` 等架构。
- 支持 NS、CS 及存在于对应发行版的 EPEL/EPKL 扩展仓库。
- 支持 gzip、bzip2、xz、Zstandard 仓库元数据。
- 支持包名模糊搜索和 `*`、`?` 通配符。
- 支持从 UTF-8、UTF-8 BOM 或 GB18030 TXT 文件导入多个包名。
- 版本筛选可选；结果按仓库、RPM 版本、包名排序。
- 仓库索引支持不缓存、1 小时、24 小时或 7 天缓存，并可一键清除。
- 搜索选项区与结果区由垂直分隔条分开，可上下拖动调整大小。
- “开始下载”只创建后台下载任务；“下载内容”打开任务管理窗口。
- 下载内容窗口展示逐包进度，支持暂停全部、恢复全部；关闭窗口不停止下载。
- 最多 4 个线程并发下载，完成前校验文件长度和仓库摘要。

## 仓库结构

NS 主仓库：

```text
https://update.cs2c.com.cn/NS/<V10|V11>/<发行版>/<组件>/adv/lic/<base|updates>/<架构>/
```

CS 主仓库示例：

```text
https://update.cs2c.com.cn/CS/V10/V10SP3/hwy/os/adv/lic/<base|updates>/<架构>/
https://update.cs2c.com.cn/CS/V10/V10SP3-2403/<组件>/os/adv/lic/<base|updates>/<架构>/
```

EPKL 扩展仓库：

```text
https://eps-server.openkylin.top/NS/<V10|V11>/<发行版>/EPKL/main/<架构>/
https://eps-server.openkylin.top/NS/<V10|V11>/<发行版>/EPKL/update/main/<架构>/
```

## 运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m src.main
```

## 打包与安装

```bash
./build.sh 1.1.0
sudo dpkg -i dist/kylin-server-rpm-search_1.1.0_all.deb
```

安装脚本会刷新桌面应用和 hicolor 图标缓存。安装后可从应用菜单启动，或运行：

```bash
kylin-server-rpm-search
```

仓库缓存位于 `~/.cache/kylin-server-rpm-search/`。

## 项目地址

https://github.com/ziyiliunian/search_rpm
