from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import mss
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageTk

from .detector import DetectionError, DetectionResult, detect_outlier

APP_NAME = "ColorGame 色块识别器"
CONFIG_DIR = Path.home() / ".colorgame"
CONFIG_FILE = CONFIG_DIR / "config.json"
TRANSPARENT_KEY = "#010203"


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _capture_region(region: tuple[int, int, int, int]) -> Image.Image:
    left, top, width, height = region
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return Image.frombytes("RGB", shot.size, shot.rgb)


def _capture_virtual_desktop() -> tuple[Image.Image, tuple[int, int, int, int]]:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    return image, (monitor["left"], monitor["top"], monitor["width"], monitor["height"])


class RegionSelector:
    def __init__(self, master: tk.Tk, on_selected, on_cancel) -> None:
        self.master = master
        self.on_selected = on_selected
        self.on_cancel = on_cancel
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.image_ref = None

        desktop, (left, top, width, height) = _capture_virtual_desktop()
        self.left = left
        self.top = top
        self.width = width
        self.height = height

        darkened = ImageEnhance.Brightness(desktop).enhance(0.45)
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry(f"{width}x{height}{left:+d}{top:+d}")
        self.window.configure(cursor="crosshair")

        self.canvas = tk.Canvas(self.window, width=width, height=height, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.image_ref = ImageTk.PhotoImage(darkened)
        self.canvas.create_image(0, 0, anchor="nw", image=self.image_ref)
        self.canvas.create_text(
            width // 2,
            34,
            text="拖动鼠标框选全部色块区域 · Esc 取消",
            fill="white",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.window.bind("<Escape>", self._cancel)
        self.window.focus_force()

    def _on_press(self, event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#ff3b30",
            width=4,
        )

    def _on_drag(self, event) -> None:
        if self.rect_id is not None:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _on_release(self, event) -> None:
        x1, x2 = sorted((self.start_x, event.x))
        y1, y2 = sorted((self.start_y, event.y))
        width = x2 - x1
        height = y2 - y1
        if width < 40 or height < 40:
            messagebox.showwarning("选择区域太小", "请框选包含全部色块的区域。", parent=self.window)
            return
        region = (self.left + x1, self.top + y1, width, height)
        self.window.destroy()
        self.master.after(140, lambda: self.on_selected(region))

    def _cancel(self, _event=None) -> None:
        self.window.destroy()
        self.on_cancel()


class ColorGameApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("760x720")
        self.root.minsize(650, 580)
        self.root.attributes("-topmost", True)

        self.region: tuple[int, int, int, int] | None = None
        self.last_result: DetectionResult | None = None
        self.last_image: Image.Image | None = None
        self.preview_ref = None
        self.highlight_window: tk.Toplevel | None = None
        self.hotkey_listener = None

        self._load_config()
        self._build_ui()
        self._start_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="ColorGame 色块识别器", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="手动框选游戏色块区域，程序会读取每个方块的 RGB 与亮度，并标出异常方块。",
            wraplength=700,
        ).pack(anchor="w", pady=(4, 14))

        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        ttk.Button(controls, text="1. 选择区域并识别", command=self.select_and_scan).pack(side="left", padx=(0, 8))
        self.rescan_button = ttk.Button(controls, text="2. 重新识别相同区域 (F8)", command=self.scan_saved_region)
        self.rescan_button.pack(side="left", padx=(0, 8))
        self.move_button = ttk.Button(controls, text="移动鼠标到目标", command=self.move_mouse_to_target)
        self.move_button.pack(side="left")

        self.keep_top_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            outer,
            text="窗口保持最前",
            variable=self.keep_top_var,
            command=lambda: self.root.attributes("-topmost", self.keep_top_var.get()),
        ).pack(anchor="w", pady=(10, 4))

        self.status_var = tk.StringVar(value="请选择游戏色块区域。")
        ttk.Label(outer, textvariable=self.status_var, foreground="#1f5c99").pack(anchor="w", pady=(4, 10))

        result_frame = ttk.LabelFrame(outer, text="识别结果", padding=12)
        result_frame.pack(fill="x", pady=(0, 12))
        self.result_var = tk.StringVar(value="尚未识别")
        ttk.Label(
            result_frame,
            textvariable=self.result_var,
            font=("Consolas", 11),
            justify="left",
        ).pack(anchor="w")

        preview_frame = ttk.LabelFrame(outer, text="识别预览", padding=8)
        preview_frame.pack(fill="both", expand=True)
        self.preview_label = ttk.Label(preview_frame, anchor="center")
        self.preview_label.pack(fill="both", expand=True)

        tips = (
            "建议：框选时只包含完整色块网格，尽量不要把关卡文字、按钮或其他图形一起框入。"
            "首次选择后，可把窗口放在一旁，按 F8 重复识别同一区域。"
        )
        ttk.Label(outer, text=tips, wraplength=700, foreground="#666666").pack(anchor="w", pady=(10, 0))

        self._update_buttons()

    def _load_config(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            region = data.get("region")
            if isinstance(region, list) and len(region) == 4 and all(isinstance(v, int) for v in region):
                self.region = tuple(region)
        except (OSError, ValueError, TypeError):
            self.region = None

    def _save_config(self) -> None:
        if not self.region:
            return
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps({"region": list(self.region)}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _start_hotkey(self) -> None:
        try:
            from pynput import keyboard

            self.hotkey_listener = keyboard.GlobalHotKeys({"<f8>": lambda: self.root.after(0, self.scan_saved_region)})
            self.hotkey_listener.start()
        except Exception:
            self.hotkey_listener = None

    def _close(self) -> None:
        if self.hotkey_listener is not None:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        self._destroy_highlight()
        self.root.destroy()

    def _update_buttons(self) -> None:
        state = "normal" if self.region else "disabled"
        self.rescan_button.configure(state=state)
        self.move_button.configure(state="normal" if self.last_result else "disabled")

    def select_and_scan(self) -> None:
        self._destroy_highlight()
        self.root.withdraw()
        try:
            RegionSelector(self.root, self._region_selected, self._selection_cancelled)
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror("无法选择屏幕区域", str(exc), parent=self.root)

    def _selection_cancelled(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.status_var.set("已取消区域选择。")

    def _region_selected(self, region: tuple[int, int, int, int]) -> None:
        self.region = region
        self._save_config()
        self.root.deiconify()
        self.root.lift()
        self._update_buttons()
        self.scan_saved_region()

    def scan_saved_region(self) -> None:
        if not self.region:
            messagebox.showinfo("尚未选择区域", "请先点击“选择区域并识别”。", parent=self.root)
            return
        self._destroy_highlight()
        self.status_var.set("正在截屏并分析色块……")
        self.root.update_idletasks()
        self.root.after(80, self._perform_scan)

    def _perform_scan(self) -> None:
        assert self.region is not None
        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError as exc:
            self.status_var.set("识别失败。")
            messagebox.showwarning("识别失败", str(exc), parent=self.root)
            return
        except Exception as exc:
            self.status_var.set("识别时发生错误。")
            messagebox.showerror("程序错误", f"识别过程中发生错误：\n{exc}", parent=self.root)
            return

        self.last_image = image
        self.last_result = result
        self._show_result(image, result)
        self._show_highlight(result)
        self._update_buttons()

    def _show_result(self, image: Image.Image, result: DetectionResult) -> None:
        target = result.target
        common_hex = "#{:02X}{:02X}{:02X}".format(*result.common_rgb)
        target_hex = "#{:02X}{:02X}{:02X}".format(*target.rgb)
        rgb_diff = tuple(target.rgb[i] - result.common_rgb[i] for i in range(3))
        brightness_diff = target.brightness - result.common_brightness
        self.result_var.set(
            f"网格：{result.rows} 行 × {result.cols} 列\n"
            f"目标：第 {target.row + 1} 行，第 {target.col + 1} 列\n"
            f"目标 RGB：{target.rgb}  {target_hex}\n"
            f"常见 RGB：{result.common_rgb}  {common_hex}\n"
            f"RGB 差值：({rgb_diff[0]:+d}, {rgb_diff[1]:+d}, {rgb_diff[2]:+d})\n"
            f"目标亮度：{target.brightness:.3f} / 100\n"
            f"常见亮度：{result.common_brightness:.3f} / 100\n"
            f"亮度差值：{brightness_diff:+.3f}\n"
            f"置信度：{result.confidence:.1f}%"
        )
        self.status_var.set(f"已找到异常方块：第 {target.row + 1} 行，第 {target.col + 1} 列。")

        preview = image.copy()
        draw = ImageDraw.Draw(preview)
        x, y, w, h = target.box
        line_width = max(3, min(w, h) // 16)
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 0, 0), width=line_width)
        draw.rectangle((x, max(0, y - 26), x + 150, y), fill=(255, 0, 0))
        draw.text((x + 5, max(0, y - 23)), f"R{target.row + 1} C{target.col + 1}", fill=(255, 255, 255))

        max_w, max_h = 700, 390
        preview.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self.preview_ref = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_ref)

    def _show_highlight(self, result: DetectionResult) -> None:
        if not self.region:
            return
        left, top, width, height = self.region
        target = result.target
        window = tk.Toplevel(self.root)
        self.highlight_window = window
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.geometry(f"{width}x{height}{left:+d}{top:+d}")
        window.configure(bg=TRANSPARENT_KEY)
        try:
            window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            window.attributes("-alpha", 0.35)

        canvas = tk.Canvas(window, width=width, height=height, bg=TRANSPARENT_KEY, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        x, y, w, h = target.box
        outline_width = max(4, min(w, h) // 15)
        canvas.create_rectangle(x, y, x + w, y + h, outline="#ff0000", width=outline_width)
        label = f"第 {target.row + 1} 行 / 第 {target.col + 1} 列"
        canvas.create_rectangle(x, max(0, y - 30), x + 190, y, fill="#ff0000", outline="#ff0000")
        canvas.create_text(x + 8, max(1, y - 26), anchor="nw", text=label, fill="white", font=("Microsoft YaHei UI", 11, "bold"))
        window.update_idletasks()
        self._make_click_through(window)
        window.after(3200, self._destroy_highlight)

    def _make_click_through(self, window: tk.Toplevel) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
            )
        except Exception:
            pass

    def _destroy_highlight(self) -> None:
        if self.highlight_window is not None:
            try:
                self.highlight_window.destroy()
            except tk.TclError:
                pass
            self.highlight_window = None

    def move_mouse_to_target(self) -> None:
        if not self.region or not self.last_result:
            return
        left, top, _, _ = self.region
        x, y = self.last_result.target.center
        screen_x, screen_y = left + x, top + y
        if sys.platform == "win32":
            ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
        else:
            messagebox.showinfo("提示", f"目标屏幕坐标：({screen_x}, {screen_y})", parent=self.root)


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    ColorGameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
