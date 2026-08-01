from __future__ import annotations

import ctypes
import json
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np

from .app import CONFIG_DIR, CONFIG_FILE, ColorGameApp, _capture_region, _enable_windows_dpi_awareness
from .automation import BoardSignature, board_has_changed
from .detector import DetectionError, DetectionResult, detect_outlier

MAX_AUTO_CLICKS = 2
VERIFY_DELAY_MS = 520
SECOND_VERIFY_DELAY_MS = 560


class AutoColorGameApp(ColorGameApp):
    """ColorGame UI with bounded automatic click and one retry."""

    def __init__(self, root: tk.Tk) -> None:
        self.busy = False
        self.auto_click_enabled = False
        super().__init__(root)
        self.root.geometry("780x790")
        self.root.minsize(680, 650)

    def _load_config(self) -> None:
        super()._load_config()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.auto_click_enabled = bool(data.get("auto_click", False))
        except (OSError, ValueError, TypeError):
            self.auto_click_enabled = False

    def _save_config(self) -> None:
        if not self.region:
            return
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            auto_click = bool(
                getattr(self, "auto_click_var", None) and self.auto_click_var.get()
            )
            data = {"region": list(self.region), "auto_click": auto_click}
            CONFIG_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _build_ui(self) -> None:
        super()._build_ui()
        outer = self.root.winfo_children()[0]
        children = outer.winfo_children()
        before_widget = children[-1] if children else None

        automation_frame = ttk.LabelFrame(outer, text="自动点击", padding=10)
        pack_options = {"fill": "x", "pady": (10, 4)}
        if before_widget is not None:
            pack_options["before"] = before_widget
        automation_frame.pack(**pack_options)

        self.auto_click_var = tk.BooleanVar(value=self.auto_click_enabled)
        self.auto_click_check = ttk.Checkbutton(
            automation_frame,
            text=f"识别成功后立即点击目标（单次任务最多点击 {MAX_AUTO_CLICKS} 次）",
            variable=self.auto_click_var,
            command=self._auto_click_setting_changed,
        )
        self.auto_click_check.pack(anchor="w")
        ttk.Label(
            automation_frame,
            text=(
                "第一次点击后若棋盘没有切换，通常表示识别错误并损失爱心；"
                "程序会重新识别并只再点击一次，然后强制停止。"
            ),
            wraplength=700,
            foreground="#8a4b08",
        ).pack(anchor="w", pady=(4, 0))
        self._update_buttons()

    def _auto_click_setting_changed(self) -> None:
        self.auto_click_enabled = self.auto_click_var.get()
        self._save_config()
        if self.auto_click_enabled:
            self.status_var.set(
                f"自动点击已开启：每次识别任务最多点击 {MAX_AUTO_CLICKS} 次。"
            )
        else:
            self.status_var.set("自动点击已关闭，只标记目标方块。")

    def _update_buttons(self) -> None:
        super()._update_buttons()
        if not hasattr(self, "auto_click_check"):
            return
        self.auto_click_check.configure(state="disabled" if self.busy else "normal")
        if self.busy:
            self.rescan_button.configure(state="disabled")
            self.move_button.configure(state="disabled")

    def select_and_scan(self) -> None:
        if self.busy:
            return
        super().select_and_scan()

    def scan_saved_region(self) -> None:
        if self.busy:
            self.status_var.set("当前识别任务尚未结束，请勿连续触发。")
            return
        if not self.region:
            messagebox.showinfo(
                "尚未选择区域",
                "请先点击“选择区域并识别”。",
                parent=self.root,
            )
            return

        self.busy = True
        self._destroy_highlight()
        self._update_buttons()
        self.status_var.set("正在截屏并分析色块……")
        self.root.update_idletasks()
        if self.auto_click_var.get():
            self.root.withdraw()
        self.root.after(80, self._perform_scan)

    def _perform_scan(self) -> None:
        assert self.region is not None
        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError as exc:
            self._finish_task("识别失败。")
            messagebox.showwarning("识别失败", str(exc), parent=self.root)
            return
        except Exception as exc:
            self._finish_task("识别时发生错误。")
            messagebox.showerror(
                "程序错误",
                f"识别过程中发生错误：\n{exc}",
                parent=self.root,
            )
            return

        self.last_image = image
        self.last_result = result
        self._show_result(image, result)

        if not self.auto_click_var.get():
            self._show_highlight(result)
            self._finish_task(
                f"已找到异常方块：第 {result.target.row + 1} 行，"
                f"第 {result.target.col + 1} 列。"
            )
            return

        self.status_var.set(
            f"已识别目标，正在自动点击第 1 次：第 {result.target.row + 1} 行，"
            f"第 {result.target.col + 1} 列。"
        )
        self._click_target(result)
        before = BoardSignature.from_result(result)
        self.root.after(
            VERIFY_DELAY_MS,
            lambda: self._verify_first_click(before, allow_wait=True),
        )

    def _verify_first_click(
        self,
        before: BoardSignature,
        *,
        allow_wait: bool,
    ) -> None:
        assert self.region is not None
        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError:
            if allow_wait:
                self.status_var.set("点击后画面正在变化，稍候确认……")
                self.root.after(
                    240,
                    lambda: self._verify_first_click(before, allow_wait=False),
                )
                return
            self._finish_task("点击后棋盘处于切换状态，已停止，不会继续点击。")
            return
        except Exception as exc:
            self._finish_task(f"点击后验证失败，已停止：{exc}")
            return

        after = BoardSignature.from_result(result)
        if board_has_changed(before, after):
            self._finish_task("自动点击成功，棋盘已切换；本次任务结束。")
            return

        self.last_image = image
        self.last_result = result
        self._show_result(image, result)
        self.status_var.set(
            "第一次点击后棋盘未切换，可能爱心减少；"
            "正在重新识别并执行最后一次点击。"
        )
        self._click_target(result)
        self.root.after(
            SECOND_VERIFY_DELAY_MS,
            lambda: self._verify_second_click(after),
        )

    def _verify_second_click(self, before: BoardSignature) -> None:
        assert self.region is not None
        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError:
            self._finish_task("第二次点击后画面正在切换；已达到 2 次上限并停止。")
            return
        except Exception as exc:
            self._finish_task(
                f"第二次点击后验证失败；已达到 2 次上限并停止：{exc}"
            )
            return

        if board_has_changed(before, BoardSignature.from_result(result)):
            self._finish_task("第二次点击成功，棋盘已切换；已停止，不会继续点击。")
        else:
            self._finish_task(
                "第二次点击后棋盘仍未切换；已达到 2 次上限并强制停止。"
            )

    def _click_target(self, result: DetectionResult) -> None:
        if not self.region:
            return
        self._destroy_highlight()
        left, top, _, _ = self.region
        x, y = result.target.center
        screen_x, screen_y = left + x, top + y

        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            user32.SetCursorPos(screen_x, screen_y)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        else:
            from pynput.mouse import Button, Controller

            mouse = Controller()
            mouse.position = (screen_x, screen_y)
            mouse.click(Button.left, 1)

    def _finish_task(self, status: str) -> None:
        self.status_var.set(status)
        self.busy = False
        if not self.root.winfo_viewable():
            self.root.deiconify()
            self.root.lift()
        self._update_buttons()


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    AutoColorGameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
