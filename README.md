# ColorGame 色块识别器

ColorGame 是一个使用 Python 编写的 Windows 桌面工具。用户手动框选屏幕上的色块网格后，程序会读取每个方块的 RGB、Lab 色彩差异和相对亮度，找出与其他方块不同的那个方块，并在屏幕及预览图中标记位置。

参考游戏：`https://colorfind.trickle.host/`

## 下载 Windows EXE

打开仓库右侧 **Releases**，进入 **ColorGame 最新 Windows 版**，下载：

- `ColorGame.exe`：免安装程序，无需安装 Python。
- `SHA256SUMS.txt`：文件完整性校验值。

最新版本发布页：`https://github.com/snailjayxxx/ColorGame-sun/releases/latest`

> Windows 第一次运行未签名的开源 EXE 时，SmartScreen 可能显示保护提示。可先核对 SHA-256，再选择“更多信息 → 仍要运行”。

## 使用方法

1. 打开需要识别的色块游戏，并让全部色块显示在屏幕上。
2. 运行 `ColorGame.exe`。
3. 点击 **选择区域并识别**。
4. 拖动鼠标，尽量只框选完整的色块网格，不要包含关卡文字和底部按钮。
5. 程序会显示异常方块的行列位置、RGB、亮度、差值和置信度。
6. 需要自动操作时，勾选 **识别成功后立即点击目标**。
7. 程序第一次点击后会确认棋盘是否切换；若棋盘未切换（通常表示识别错误并损失爱心），会重新识别并只再点击一次。
8. 每次手动识别或按 F8 触发的任务最多点击 2 次，不会无限循环点击。
9. 未开启自动点击时，仍可点击 **移动鼠标到目标**，只移动指针而不点击。

## 识别方法

程序不是针对某一张训练图片写死坐标，而是实时分析用户选中的屏幕区域：

1. 使用多种二值化方式分离色块与背景。
2. 根据面积、长宽比、尺寸一致性和网格排列筛选方块组。
3. 从每个方块中央区域取中位 RGB，避开圆角、边缘抗锯齿和阴影。
4. 将 RGB 转换到 Lab 色彩空间，并计算相对亮度。
5. 通过方块之间的成对中位距离寻找离群值，而不是只与某个固定颜色比较。
6. 未启用自动点击时，在原屏幕位置短暂显示红框，同时在程序内保留结果预览。
7. 启用自动点击时，识别完成后立即点击；随后比较点击前后的棋盘指纹，判断是否成功进入下一关。
8. 若棋盘未变化，只允许重新识别并再点击一次，达到 2 次后无条件停止。

这种方法可适应不同颜色、不同网格数量、显示缩放和轻微截图压缩，但框选区域仍应尽量干净。

## 从源码运行

要求：Python 3.10 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python run.py
```

运行测试：

```powershell
python -m pytest
```

## 本地构建 EXE

Windows 双击：

```text
build_exe.bat
```

或手动执行：

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ColorGame --collect-all pynput run.py
```

生成文件位于：

```text
dist\ColorGame.exe
```

## 自动构建与发布

`.github/workflows/build-windows.yml` 会在以下情况运行：

- 推送到 `main`：测试、构建 EXE、上传 Actions Artifact，并更新 `latest` Release。
- Pull Request：只测试和构建，不发布 Release。
- 手动运行：可以在 Actions 页面触发。

## 项目结构

```text
colorgame/
├─ src/colorgame/
│  ├─ app.py          # 基础 Tkinter 桌面界面与区域框选
│  ├─ auto_app.py     # 自动点击、点击验证与单次重试控制
│  ├─ automation.py   # 棋盘切换判断与自动化安全逻辑
│  └─ detector.py     # 网格检测、RGB/亮度采样与离群值算法
├─ tests/             # 合成色块测试
├─ .github/workflows/ # Windows EXE 自动构建与发布
├─ build_exe.bat
├─ pyproject.toml
└─ run.py
```

## 自动点击安全限制

- 自动点击默认关闭，需要用户主动勾选。
- 一次“选择区域并识别”或一次 F8 任务最多点击 2 次。
- 程序通过棋盘是否切换判断点击结果，不依赖特定颜色或样式的爱心图标。
- 第二次点击后无论成功与否都会停止，必须由用户再次按 F8 才能开始下一次任务。

## 已知限制

- 主要面向 Windows 10/11；源码在其他桌面系统上可运行，但屏幕高亮和移动鼠标功能以 Windows 为主。
- 方块必须基本规则排列，且与背景存在可见边界。
- 框选区域包含大量相近大小的图标、文字或其他网格时，可能影响识别。
- 多显示器采用不同缩放比例时，建议把游戏和程序放在主显示器，或把各显示器缩放设置为相同值。

## 许可

MIT License。
