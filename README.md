# Search RPM

基于 Python + PyQt5 的麒麟软件 RPM 仓库浏览与下载工具。

## 功能

- 从 `https://update.cs2c.com.cn/NS/V10/` 动态读取系统版本和 OS 目录。
- 按系统版本、OS 类型、芯片架构选择仓库。
- 默认选择 `base` 与 `updates`，解析标准 YUM/DNF `repodata/repomd.xml` 和 `primary.xml`。
- 支持包名模糊搜索和通配符搜索，例如 `kernel*`。
- 支持版本模糊搜索，例如同时输入包名 `kernel*` 和版本 `89.44`。
- 支持按仓库名过滤、批量勾选和选择下载目录。
- 下载使用 Python 标准库，带进度显示和 `.part` 临时文件保护。

## 运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m src.main
```

如果当前桌面环境缺少 Qt 平台插件，可在无界面环境使用：

```bash
QT_QPA_PLATFORM=offscreen python3 -m src.main
```

## 打包 Debian

构建流程参考 `pinginfo` 项目，使用系统 `dpkg-deb`：

```bash
./build.sh 0.1.0
sudo dpkg -i dist/search-rpm_0.1.0_all.deb
```

安装后可在应用菜单中启动，也可运行 `search-rpm`。

## 说明

目标站点的常见仓库层级为：

```text
V10/<版本>/<os 或 sm-os>/adv/lic/<base 或 updates>/<架构>/repodata/
```

不同版本可能存在目录差异，程序会优先读取目录索引；若服务器目录或元数据不存在，会在状态栏显示错误。

## 项目地址

https://github.com/ziyiliunian/search_rpm
