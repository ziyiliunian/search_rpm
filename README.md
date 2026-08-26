# 银河麒麟服务器多架构包下载工具

版本：`1.0.0`

Debian 包名：`kylin-server-rpm-search`

基于 Python + PyQt5，用于浏览、搜索和批量下载银河麒麟服务器多架构 RPM 软件包。

## 功能

- 按“系统版本 → OS 类型 → 芯片架构 → 软件仓库”完成仓库选择。
- 默认选择 `V10SP3`、`os`、`aarch64`、`base` 和 `update`。
- 支持 `aarch64`、`x86_64`、`loongarch64` 等架构。
- 支持银河麒麟主仓库及 EPEL/EPKL 扩展仓库。
- 支持包名模糊搜索和 `*`、`?` 通配符。
- 支持从 UTF-8、UTF-8 BOM 或 GB18030 编码的 TXT 文件导入多个包名。
- TXT 每行可包含一个或多个包名，支持空格、逗号或分号分隔；`#` 后内容视为注释。
- 版本筛选为可选项，匹配 `version-release`；结果按仓库、RPM 版本、包名排序。
- 仓库目录与软件包索引支持不缓存、1 小时、24 小时或 7 天缓存，并可一键清除。
- 批量下载使用最多 4 个线程，独立弹窗显示每个包和整体任务进度。
- 关闭下载弹窗不会中断下载，可返回主界面继续搜索并创建其他下载任务。
- 下载完成前校验文件长度和仓库摘要，失败时删除 `.part` 临时文件。

## 包名导入示例

```text
# 内核相关包
kernel*
kernel-devel kernel-headers
openssl, curl
```

手工输入的包名和 TXT 导入的包名按“任意一个匹配”组合。

## 仓库结构

主仓库：

```text
https://update.cs2c.com.cn/NS/V10/<版本>/<OS类型>/adv/lic/<base|updates>/<架构>/
```

EPEL/EPKL 扩展仓库：

```text
https://eps-server.openkylin.top/NS/V10/<版本>/EPKL/main/<架构>/
https://eps-server.openkylin.top/NS/V10/<版本>/EPKL/update/main/<架构>/
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
./build.sh 1.0.0
sudo dpkg -i dist/kylin-server-rpm-search_1.0.0_all.deb
```

安装后可从应用菜单启动，或运行：

```bash
kylin-server-rpm-search
```

## 缓存目录

仓库缓存保存于：

```text
~/.cache/kylin-server-rpm-search/
```

## 项目地址

https://github.com/ziyiliunian/search_rpm
