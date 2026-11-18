<p align="center"><img src="snaptext/assets/lens.png" width="120" alt="拾像 Lens"></p>

# 拾像 Lens

**截图 · 贴图 · 标注 · 离线识字**

由空天遥感数学交叉技术创新中心开发，维护账号 [li0925](https://github.com/li0925)。C 方案图标融合湘大三拱门与空天轨道。

[下载 Windows 版](https://github.com/li0925/ShixiangLens/releases) · [完整使用说明](docs/USER_GUIDE.md) · [问题反馈](https://github.com/li0925/ShixiangLens/issues)

## 一分钟上手

1. 退出 Snipaste 和旧版 SnapText，避免快捷键冲突。
2. 按 **F1** 框选截图，调整选区后按 **Enter** 复制。
3. 按 **F3** 贴到桌面；也可在截图选区内直接按 F3 贴图。
4. 在贴图上按 **空格** 打开标注工具栏。
5. **Ctrl+拖选** 识别局部文字，右键可识别整张图片。

双击隐藏贴图，托盘右键可以找回。关闭说明窗口后软件仍在托盘运行；退出请使用托盘菜单。

## 功能

- 可调整截图选区、窗口/原生控件吸附、像素放大镜和取色。
- 桌面置顶贴图、缩放、旋转、翻转、透明度、鼠标穿透和分组。
- 矩形、椭圆、箭头、画笔、文字、高亮、马赛克、高斯模糊和非破坏橡皮擦。
- RapidOCR 3.10.0 + PP-OCRv6 Small，本机离线识别，结果在贴图中编辑、复制和保存。
- 文本、HTML、颜色和图片文件贴图，支持 GIF 播放/逐帧查看。
- 首选项、快捷键设置、可选开机启动、本机备份恢复。

## 下载与运行

前往 [Releases](https://github.com/li0925/ShixiangLens/releases)，下载 `ShixiangLens-v4.1.0-win-x64.zip`，解压后运行 `拾像 Lens.exe`，无需安装 Python。首次启动和模型加载可能需要几秒钟。当前版本为首次公开测试版，EXE 暂未数字签名。

压缩包包含对应源码、许可证及使用说明。单文件 EXE 会解压运行库至系统临时目录。软件不上传截图；自动备份默认开启，保存到本机用户应用数据目录，可在首选项中关闭。内部 `SnapText` 数据目录名保留用于兼容旧版。

## 从源码运行

构建环境：64 位 Windows，Python 3.9。开发与构建依赖固定在 `requirements-lock.txt`。

```powershell
python -m venv .venv-latest
.\.venv-latest\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv-latest\Scripts\python.exe main.py
```

安装依赖需要联网；正式便携版已包含 OCR 模型，正常识别无需联网。

## 验证与打包

桌面相关检查需要可用的 Windows 交互桌面、系统字体和剪贴板。

```powershell
.\.venv-latest\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-latest\Scripts\python.exe prepare_release.py
.\.venv-latest\Scripts\python.exe -m PyInstaller SnapText.spec --noconfirm
.\.venv-latest\Scripts\python.exe package_release.py
```

构建输出位于 `dist`。`拾像 Lens.exe --verify 输出目录` 可核验实际引擎、图标和内嵌识别界面。

## 已知限制

- 目前仅支持 Windows x64。
- 一次选区暂不支持跨多个显示器；自绘网页 UI 不能保证逐元素吸附。
- OCR 输出纯文本，不恢复复杂表格和原始版式，识别结果需要检查。
- 备份最多 30 张平面 PNG；恢复后不含旧撤销历史和 GIF 播放状态。
- 尚未在另一台全新 Windows 计算机上独立验证。

## 许可证和致谢

项目源码按 **GPL-3.0-or-later** 分发，见 [LICENSE.txt](LICENSE.txt)；第三方组件许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `third-party-licenses/`。

感谢 RapidOCR、PaddleOCR、ONNX Runtime、Qt/PyQt 和相关开源项目。交互参考 Snipaste，本项目与 Snipaste 无隶属关系，不包含其程序代码或图标。

欢迎通过 Issues 报告问题，通过 Pull Requests 提交改进。请不要在截图或日志中包含密码、令牌或其他不希望公开的信息。
