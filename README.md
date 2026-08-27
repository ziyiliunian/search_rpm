# 银河麒麟服务器多架构包下载工具

版本：`1.3.0`

Debian 包名：`kylin-server-rpm-search`

基于 Python + PyQt5，用于浏览、搜索和批量下载银河麒麟服务器多架构 RPM 软件包。

## 产品源

产品源是实际仓库来源，而不是产品名称：

### 系统源

```text
https://update.cs2c.com.cn/NS/
```

- 系统版本：`V10`、`V11`。
- V10 发行版：`V10SP1`、`V10SP2`、`V10SP3`、`V10SP3-2403`。
- V11 发行版：`2503`、`V11SP1-2603`。
- 系统维护与补丁组件：通常为 `os`；V10SP3 还提供 `sm-os`。
- 软件仓库：`base`、`update`，其中 `update` 映射远程 `updates`。

### EPKL 源

```text
https://eps-server.openkylin.top/NS/
```

- V10 发行版包括 `V10SP1`、`V10SP2`、`V10SP3`、`V10SP3-2403`、`HPC`、`V10.4-HPC`、`V10AIPLUS`。
- V11 当前提供 `2503`。
- 标准软件包仓库为 `main`、`update`；部分发行版仅提供 `main`。
- 已确认的 `multi_version` 组件作为“系统维护与补丁组件”显示：
  - V10SP3、V10SP3-2403：`Compiler`、`DB`、`Storage`。
  - V11 2503：`AI`。
- EPKL 各发行版的架构、组件和仓库选项与系统源独立，不互相套用。

### CS 源

```text
https://update.cs2c.com.cn/CS/
```

- 当前仅提供系统版本 `V10`。
- 发行版为 `V10SP3`、`V10SP3-2403`。
- V10SP3 提供 `hwy/os`。
- V10SP3-2403 提供 `aiplus/os`、`ccw/os`、`gazb/os`、`lowlatency/os` 和直接仓库 `kernel-4k`。
- `ceb` 目录需要服务器认证，因此不显示为可搜索组件。

## 选择流程

```text
产品源 → 系统版本 → 发行版本号 → 系统维护与补丁组件 → 芯片架构 → 软件仓库 → 搜索 → 开始下载 → 下载内容
```

默认选择：`系统源 → V10 → V10SP3 → os → aarch64 → base/update`。

## 主要功能

- 支持多来源、V10/V11、多发行版和多架构联动。
- 支持 gzip、bzip2、xz、Zstandard 仓库元数据。
- 支持包名模糊搜索、`*`/`?` 通配符和 TXT 批量导入。
- TXT 既可填写纯包名，也可填写 `name-version-release.arch` 完整 NEVRA 或 `.rpm` 文件名；完整标识采用精确匹配。
- 版本筛选可选；结果按仓库、RPM 版本、包名排序。
- 仓库索引支持不缓存、1 小时、24 小时或 7 天缓存。
- 选择区和结果区可上下拖动调整大小。
- “开始下载”创建后台任务，“下载内容”查看、暂停或恢复任务。
- 最多 4 个线程并发下载，并校验文件长度与仓库摘要。

## 运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m src.main
```

## 打包与安装

```bash
./build.sh 1.3.0
sudo dpkg -i dist/kylin-server-rpm-search_1.3.0_all.deb
```

安装后可从应用菜单启动，或运行 `kylin-server-rpm-search`。

仓库缓存位于 `~/.cache/kylin-server-rpm-search/`。

## 项目地址

https://github.com/ziyiliunian/search_rpm
