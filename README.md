# ColorGame 色块识别器

ColorGame 是一个使用 Python 编写、可直接运行在 Windows 和 Apple Silicon Mac 上的桌面工具。用户框选屏幕上的色块网格后，程序会读取每个方块的 RGB、Lab 色彩差异和相对亮度，找出与其他方块不同的方块，并可连续自动点击进入下一关。

参考游戏：`https://colorfind.trickle.host/`

## 下载免安装程序

打开仓库右侧 **Releases**，进入 **ColorGame 最新版**。

### Windows 10/11

下载：

- `ColorGame.exe`：免安装程序，无需安装 Python。
- `SHA256SUMS.txt`：Windows 文件完整性校验值。

Windows 第一次运行未签名的开源 EXE 时，SmartScreen 可能显示保护提示。可先核对 SHA-256，再选择“更多信息 → 仍要运行”。

### Apple Silicon Mac

适用于 M1、M2、M3、M4 等 arm64 Mac，下载任意一种：

- `ColorGame-macOS-Apple-Silicon.dmg`：推荐，打开后把 `ColorGame.app` 拖入“应用程序”。
- `ColorGame-macOS-Apple-Silicon.zip`：解压后直接得到 `ColorGame.app`。
- `SHA256SUMS-macOS.txt`：Mac 文件完整性校验值。

Mac 用户无需安装 Python。此公开构建采用固定 Bundle ID 和 ad-hoc 签名，但未使用付费 Apple Developer ID 公证。第一次打开时，可在 Finder 中右键 `ColorGame.app`，选择“打开”，然后确认运行。

第一次使用还需要在 **系统设置 → 隐私与安全性** 中允许：

1. **屏幕与系统音频录制**：用于读取用户手动框选的屏幕区域。
2. **辅助功能**：用于移动鼠标、自动点击以及全局 F8/F9 快捷键。

修改权限后请退出并重新打开 ColorGame。

最新版本发布页：`https://github.com/snailjayxxx/ColorGame-sun/releases/latest`

## 连续自动运行

1. 打开色块游戏，让全部方块显示在屏幕上。
2. 运行 `ColorGame.exe` 或 `ColorGame.app`。
3. 勾选 **选择区域后连续自动识别并点击**。
4. 点击 **选择区域并识别**，只框选完整色块网格，不要包含关卡文字和底部按钮。
5. 程序会立即识别并点击目标方块。
6. 棋盘切换后，程序自动识别新一关并继续点击，不需要重复按 F8。
7. 运行中按 **F9** 可随时停止，程序窗口会重新显示。

连续模式的每一关都有独立安全限制：

- 每关第一次点击后，程序会持续确认棋盘是否切换。
- 棋盘切换成功后，才会进入下一关并执行新一次识别。
- 若棋盘一直没有切换，通常表示点错并损失爱心；程序会重新识别并只再点击一次。
- 第二次点击后仍未切换，会停止整个连续任务，不会第三次点击，也不会无限消耗爱心。
- 点击后无法可靠识别棋盘状态时，也会安全停止，而不是盲目继续点击。

## 单次识别模式

取消勾选连续自动运行后：

1. 选择色块区域。
2. 程序只识别并标记当前异常方块，不会自动点击。
3. 可以按 **F8** 重新识别相同区域。
4. 可以点击 **移动鼠标到目标**，只移动指针而不点击。

## 识别方法

程序不是针对某一张训练图片写死坐标，而是实时分析用户选中的屏幕区域：

1. 使用多种二值化方式分离色块与背景。
2. 根据面积、长宽比、尺寸一致性和网格排列筛选方块组。
3. 从每个方块中央区域取中位 RGB，避开圆角、边缘抗锯齿和阴影。
4. 将 RGB 转换到 Lab 色彩空间，并计算相对亮度。
5. 通过方块之间的成对中位距离寻找离群值。
6. 自动点击后比较点击前后的棋盘指纹，判断是否进入下一关。

这种方法可适应不同颜色、不同网格数量、显示缩放和轻微截图压缩，但框选区域仍应尽量干净。

## 快捷键

- **F8**：使用已保存区域开始识别；开启连续模式时会开始连续运行。
- **F9**：立即停止当前连续任务。

Mac 键盘默认把 F8/F9 用作媒体键时，需要同时按 `fn`，或者在系统键盘设置中启用“将 F1、F2 等键用作标准功能键”。

## 从源码运行

要求：Python 3.10 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# Windows 使用：.venv\Scripts\activate
python -m pip install -e ".[dev]"
python run.py
```

运行测试：

```bash
python -m pytest
```

## 本地构建 Windows EXE

Windows 双击：

```text
build_exe.bat
```

生成文件位于：

```text
dist\ColorGame.exe
```

## 本地构建 Apple Silicon Mac App

在 M 芯片 Mac 的终端中执行：

```bash
chmod +x build_macos.sh
./build_macos.sh
```

脚本会运行测试，并生成：

```text
dist/ColorGame.app
dist/ColorGame-macOS-Apple-Silicon.dmg
dist/ColorGame-macOS-Apple-Silicon.zip
dist/SHA256SUMS-macOS.txt
```

PyInstaller 不是跨平台编译器，因此 Windows EXE 在 Windows runner 构建，Mac arm64 App 在 GitHub 的 Apple Silicon macOS runner 构建。

## 自动构建与发布

- `.github/workflows/build-windows.yml`：测试并构建 Windows EXE。
- `.github/workflows/build-macos-arm64.yml`：在 arm64 macOS runner 上测试并构建 `.app`、DMG 和 ZIP。
- 推送到 `main` 后，两套构建产物都会上传到同一个 `latest` Release。
- Pull Request 只测试和构建，不发布 Release。

## 项目结构

```text
colorgame/
├─ src/colorgame/
│  ├─ app.py          # 基础 Tkinter 桌面界面与区域框选
│  ├─ auto_app.py     # 连续自动识别、点击、停止与重试控制
│  ├─ automation.py   # 棋盘切换判断与点击决策状态机
│  └─ detector.py     # 网格检测、RGB/亮度采样与离群值算法
├─ tests/             # 合成色块和自动化状态测试
├─ .github/workflows/ # Windows 与 Apple Silicon 自动构建
├─ build_exe.bat
├─ build_macos.sh
├─ pyproject.toml
└─ run.py
```

## 已知限制

- Mac 自动点击依赖用户授予“屏幕与系统音频录制”和“辅助功能”权限。
- 当前 Mac Release 是 Apple Silicon arm64 原生版本，不支持老款 Intel Mac。
- 方块必须基本规则排列，且与背景存在可见边界。
- 框选区域包含文字、按钮或其他相近大小图形时，可能影响识别。
- 多显示器采用不同缩放比例时，建议把游戏和程序放在主显示器，或统一各显示器缩放比例。
- 连续运行依赖棋盘画面发生可检测变化；极少数前后两关视觉信息几乎完全相同的情况，程序可能为了保护爱心而停止。

## 许可

MIT License。
