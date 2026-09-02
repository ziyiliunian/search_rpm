# 银河麒麟服务器多架构包下载工具

版本：`1.6.1`

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
- 新增独立“EPKL 仓库分类”下拉：`main`、`update`、`multi_version`。
- 选择 `main` 或 `update` 后，维护组件显示“标准软件包”。
- 选择 `multi_version` 后，维护组件从远程目录动态发现，不再局限于内置列表。
- 支持组件下继续出现模块、版本等额外目录层级，并按需显示“组件子目录”和“扩展子目录”下拉。
- 例如：`ContainerTools → module-docker-ce-20 → aarch64`。
- 最终仓库 RPM 数量少于等于 30 个时，下拉选择完成后自动显示全部包。
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
系统源/EPKL 源/CS 源：产品源 → 版本/目录层级 → 系统维护与补丁组件 → 软件仓库 → 芯片架构 → 搜索 → 开始下载 → 下载内容
自定义源：产品源 → 源目录选择（源目录1至源目录5） → 搜索 → 开始下载 → 下载内容
```

默认选择：`系统源 → V10 → V10SP3 → os → aarch64 → base/update`。

## 主要功能

- 支持多来源、V10/V11、多发行版和多架构联动。
- 软件仓库使用单选下拉；切换来源、目录、组件、仓库或架构会立即清空旧结果。
- 支持 HTTPS 自定义源，按“目录1”至“目录5”逐层发现，检测到 `repodata/repomd.xml` 后自动解析。
- 搜索结果中的下载地址可双击选择，也可通过“复制地址”按钮复制。
- 支持 gzip、bzip2、xz、Zstandard 仓库元数据。
- 支持包名模糊搜索、`*`/`?` 通配符和 TXT 批量导入。
- TXT 既可填写纯包名，也可填写 `name-version-release.arch` 完整 NEVRA 或 `.rpm` 文件名；完整标识采用精确匹配。
- 版本筛选可选；结果按仓库、RPM 版本、包名排序。
- 仓库索引支持不缓存、1 小时、24 小时或 7 天缓存。
- 缓存采用 gzip JSON Lines 磁盘流式格式，逐条读写，避免整份缓存进入内存。
- 搜索在后台逐包筛选并释放整库数据；大型仓库禁止空条件搜索。
- 选择区和结果区可上下拖动调整大小。
- “开始下载”创建后台任务，“下载内容”查看、暂停或恢复任务。
- 最多 4 个线程并发下载，并强制使用 HTTPS、校验文件长度与仓库摘要。
- 仓库元数据具有下载大小、解压大小、URL 边界和缓存完整性校验。

## 运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m src.main
```

## 打包与安装

```bash
./build.sh 1.6.1
sudo dpkg -i dist/kylin-server-rpm-search_1.6.1_all.deb
```

安装后可从应用菜单启动，或运行 `kylin-server-rpm-search`。

仓库缓存位于 `~/.cache/kylin-server-rpm-search/`。

## 项目地址

https://github.com/ziyiliunian/search_rpm
