from __future__ import annotations

import ctypes
import json
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np

from .app import CONFIG_DIR, CONFIG_FILE, ColorGameApp, _capture_region, _enable_windows_dpi_awareness
from .automation import BoardSignature, ClickDecision, board_has_changed, decide_click_action
from .detector import DetectionError, DetectionResult, detect_outlier

MAX_CLICKS_PER_LEVEL = 2
VERIFY_INITIAL_DELAY_MS = 320
VERIFY_POLL_MS = 120
MAX_VERIFY_POLLS = 12
NEXT_LEVEL_DELAY_MS = 90
LEVEL_SCAN_RETRY_MS = 100
MAX_LEVEL_SCAN_POLLS = 12


class AutoColorGameApp(ColorGameApp):
    """ColorGame UI with continuous, bounded automatic play."""

    def __init__(self, root: tk.Tk) -> None:
        self.busy = False
        self.continuous_running = False
        self.stop_requested = False
        self.auto_click_enabled = False
        self.session_id = 0
        self.level_number = 0
        self.levels_completed = 0
        self.total_clicks = 0
        super().__init__(root)
        self.root.geometry("800x820")
        self.root.minsize(700, 680)

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

        automation_frame = ttk.LabelFrame(outer, text="连续自动运行", padding=10)
        pack_options = {"fill": "x", "pady": (10, 4)}
        if before_widget is not None:
            pack_options["before"] = before_widget
        automation_frame.pack(**pack_options)

        self.auto_click_var = tk.BooleanVar(value=self.auto_click_enabled)
        self.auto_click_check = ttk.Checkbutton(
            automation_frame,
            text=(
                "选择区域后连续自动识别并点击"
                f"（每关最多点击 {MAX_CLICKS_PER_LEVEL} 次）"
            ),
            variable=self.auto_click_var,
            command=self._auto_click_setting_changed,
        )
        self.auto_click_check.pack(anchor="w")

        button_row = ttk.Frame(automation_frame)
        button_row.pack(fill="x", pady=(8, 0))
        self.stop_button = ttk.Button(
            button_row,
            text="停止连续运行 (F9)",
            command=self.stop_continuous,
        )
        self.stop_button.pack(side="left")

        self.run_stats_var = tk.StringVar(value="尚未开始连续运行。")
        ttk.Label(
            button_row,
            textvariable=self.run_stats_var,
            foreground="#1f5c99",
        ).pack(side="left", padx=(12, 0))

        ttk.Label(
            automation_frame,
            text=(
                "每关识别后立即点击；确认棋盘切换后自动开始下一关。"
                "若第一次点击后棋盘一直未切换，只重新识别并再点击一次；"
                "第二次仍未切换就停止整个连续任务，避免持续消耗爱心。"
                "运行中可随时按 F9 停止。"
            ),
            wraplength=720,
            foreground="#8a4b08",
        ).pack(anchor="w", pady=(6, 0))
        self._update_buttons()

    def _start_hotkey(self) -> None:
        try:
            from pynput import keyboard

            self.hotkey_listener = keyboard.GlobalHotKeys(
                {
                    "<f8>": lambda: self.root.after(0, self.scan_saved_region),
                    "<f9>": lambda: self.root.after(0, self.stop_continuous),
                }
            )
            self.hotkey_listener.start()
        except Exception:
            self.hotkey_listener = None

    def _close(self) -> None:
        self.stop_requested = True
        self.continuous_running = False
        self.session_id += 1
        super()._close()

    def _auto_click_setting_changed(self) -> None:
        self.auto_click_enabled = self.auto_click_var.get()
        self._save_config()
        if self.auto_click_enabled:
            self.status_var.set(
                "连续自动运行已开启：选择区域或按 F8 后，会持续识别后续关卡。"
            )
        else:
            self.status_var.set("连续自动运行已关闭，只识别并标记一个目标。")

    def _update_buttons(self) -> None:
        super()._update_buttons()
        if not hasattr(self, "auto_click_check"):
            return

        running = self.busy or self.continuous_running
        self.auto_click_check.configure(state="disabled" if running else "normal")
        self.stop_button.configure(
            state="normal" if self.continuous_running else "disabled"
        )
        if running:
            self.rescan_button.configure(state="disabled")
            self.move_button.configure(state="disabled")

    def select_and_scan(self) -> None:
        if self.busy or self.continuous_running:
            self.status_var.set("连续任务正在运行；请先按 F9 停止。")
            return
        super().select_and_scan()

    def scan_saved_region(self) -> None:
        if self.busy or self.continuous_running:
            self.status_var.set("当前任务正在运行；请先按 F9 停止。")
            return
        if not self.region:
            messagebox.showinfo(
                "尚未选择区域",
                "请先点击“选择区域并识别”。",
                parent=self.root,
            )
            return

        self._destroy_highlight()
        self.stop_requested = False
        self.session_id += 1
        session_id = self.session_id

        if self.auto_click_var.get():
            self._start_continuous_session(session_id)
        else:
            self.busy = True
            self._update_buttons()
            self.status_var.set("正在截屏并分析色块……")
            self.root.after(80, lambda: self._perform_manual_scan(session_id))

    def _start_continuous_session(self, session_id: int) -> None:
        self.busy = True
        self.continuous_running = True
        self.level_number = 0
        self.levels_completed = 0
        self.total_clicks = 0
        self._update_run_stats()
        self._update_buttons()
        self.status_var.set(
            "连续自动运行已开始。正在识别第 1 关；按 F9 可随时停止。"
        )
        self.root.update_idletasks()
        self.root.withdraw()
        self.root.after(
            60,
            lambda: self._scan_level(session_id, scan_poll=0),
        )

    def stop_continuous(self) -> None:
        if not self.continuous_running and not self.busy:
            return

        self.stop_requested = True
        self.continuous_running = False
        self.busy = False
        self.session_id += 1
        self._show_main_window()
        self.status_var.set(
            f"连续运行已由用户停止：完成 {self.levels_completed} 关，"
            f"共点击 {self.total_clicks} 次。"
        )
        self._update_run_stats()
        self._update_buttons()

    def _automation_active(self, session_id: int) -> bool:
        return (
            session_id == self.session_id
            and self.continuous_running
            and self.busy
            and not self.stop_requested
        )

    def _perform_manual_scan(self, session_id: int) -> None:
        if session_id != self.session_id:
            return
        assert self.region is not None
        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError as exc:
            self._finish_manual_task("识别失败。")
            messagebox.showwarning("识别失败", str(exc), parent=self.root)
            return
        except Exception as exc:
            self._finish_manual_task("识别时发生错误。")
            messagebox.showerror(
                "程序错误",
                f"识别过程中发生错误：\n{exc}",
                parent=self.root,
            )
            return

        self.last_image = image
        self.last_result = result
        self._show_result(image, result)
        self._show_highlight(result)
        self._finish_manual_task(
            f"已找到异常方块：第 {result.target.row + 1} 行，"
            f"第 {result.target.col + 1} 列。"
        )

    def _finish_manual_task(self, status: str) -> None:
        self.status_var.set(status)
        self.busy = False
        self._update_buttons()

    def _scan_level(self, session_id: int, *, scan_poll: int) -> None:
        if not self._automation_active(session_id):
            return
        assert self.region is not None

        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError as exc:
            if scan_poll < MAX_LEVEL_SCAN_POLLS:
                self.root.after(
                    LEVEL_SCAN_RETRY_MS,
                    lambda: self._scan_level(
                        session_id,
                        scan_poll=scan_poll + 1,
                    ),
                )
                return
            self._stop_with_status(
                session_id,
                f"连续运行已停止：等待下一关时持续无法识别棋盘（{exc}）。",
            )
            return
        except Exception as exc:
            self._stop_with_status(
                session_id,
                f"连续运行已停止：识别过程中发生错误：{exc}",
            )
            return

        self.level_number += 1
        self.last_image = image
        self.last_result = result
        self._show_result(image, result)
        self.status_var.set(
            f"第 {self.level_number} 关已识别，立即点击第 1 次："
            f"第 {result.target.row + 1} 行，第 {result.target.col + 1} 列。"
        )
        self._click_target(result)
        self.total_clicks += 1
        self._update_run_stats()

        before = BoardSignature.from_result(result)
        self.root.after(
            VERIFY_INITIAL_DELAY_MS,
            lambda: self._verify_click(
                session_id,
                before=before,
                click_number=1,
                poll_count=0,
            ),
        )

    def _verify_click(
        self,
        session_id: int,
        *,
        before: BoardSignature,
        click_number: int,
        poll_count: int,
    ) -> None:
        if not self._automation_active(session_id):
            return
        assert self.region is not None

        try:
            image = _capture_region(self.region)
            result = detect_outlier(np.asarray(image, dtype=np.uint8))
        except DetectionError:
            if poll_count < MAX_VERIFY_POLLS:
                self.root.after(
                    VERIFY_POLL_MS,
                    lambda: self._verify_click(
                        session_id,
                        before=before,
                        click_number=click_number,
                        poll_count=poll_count + 1,
                    ),
                )
                return
            self._stop_with_status(
                session_id,
                "点击后长时间无法确认棋盘状态，已安全停止，不会继续点击。",
            )
            return
        except Exception as exc:
            self._stop_with_status(
                session_id,
                f"点击后验证失败，已停止：{exc}",
            )
            return

        after = BoardSignature.from_result(result)
        decision = decide_click_action(
            board_changed=board_has_changed(before, after),
            click_number=click_number,
            poll_count=poll_count,
            max_polls=MAX_VERIFY_POLLS,
            max_clicks=MAX_CLICKS_PER_LEVEL,
        )

        if decision is ClickDecision.WAIT:
            self.root.after(
                VERIFY_POLL_MS,
                lambda: self._verify_click(
                    session_id,
                    before=before,
                    click_number=click_number,
                    poll_count=poll_count + 1,
                ),
            )
            return

        if decision is ClickDecision.NEXT_LEVEL:
            self.levels_completed += 1
            self.last_image = image
            self.last_result = result
            self._update_run_stats()
            self.status_var.set(
                f"第 {self.level_number} 关已通过；正在准备下一关。"
            )
            self.root.after(
                NEXT_LEVEL_DELAY_MS,
                lambda: self._scan_level(session_id, scan_poll=0),
            )
            return

        if decision is ClickDecision.RETRY:
            self.last_image = image
            self.last_result = result
            self._show_result(image, result)
            self.status_var.set(
                f"第 {self.level_number} 关第一次点击后棋盘未切换，"
                "可能损失爱心；已重新识别并执行最后一次点击。"
            )
            self._click_target(result)
            self.total_clicks += 1
            self._update_run_stats()
            retry_before = BoardSignature.from_result(result)
            self.root.after(
                VERIFY_INITIAL_DELAY_MS,
                lambda: self._verify_click(
                    session_id,
                    before=retry_before,
                    click_number=2,
                    poll_count=0,
                ),
            )
            return

        self._stop_with_status(
            session_id,
            f"第 {self.level_number} 关第二次点击后棋盘仍未切换；"
            "已达到每关 2 次上限并停止整个连续任务。",
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

    def _stop_with_status(self, session_id: int, status: str) -> None:
        if session_id != self.session_id:
            return
        self.stop_requested = True
        self.continuous_running = False
        self.busy = False
        self.session_id += 1
        self._show_main_window()
        self.status_var.set(status)
        self._update_run_stats()
        self._update_buttons()

    def _show_main_window(self) -> None:
        if not self.root.winfo_viewable():
            self.root.deiconify()
        self.root.lift()

    def _update_run_stats(self) -> None:
        if not hasattr(self, "run_stats_var"):
            return
        self.run_stats_var.set(
            f"已完成 {self.levels_completed} 关｜点击 {self.total_clicks} 次"
        )


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    AutoColorGameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
