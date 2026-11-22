"""APP-033 M3 preview-only desktop.

Manual START/STOP, no printer code is invoked or exposed. This is a review
build until the M2 Windows hardware and M1 image acceptance gates pass.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from m2_monitor import InboxMonitor, JobStore, ScanPipeline, SingleInstance, _paths_safe


class PreviewApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("黒カット印刷 | プレビュー専用")
        self.geometry("570x445")
        self.minsize(510, 420)
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.notifications: queue.Queue[tuple[str, str]] = queue.Queue()
        self.last_preview: Path | None = None
        self.stopping_for_exit = False
        self.config_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "BlackCutPreview" / "settings.json"

        self.inbox_value = tk.StringVar()
        self.output_value = tk.StringVar()
        self.rotation_value = tk.StringVar(value="0")
        self.status_value = tk.StringVar(value="停止中（印刷OFF）")
        self.count_value = tk.StringVar(value="処理：0件")
        self.received = 0
        self._load_settings()
        self._build_ui()
        self.after(200, self._drain_notifications)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="黒カット印刷", font=("Yu Gothic UI", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="試作版・画像加工の確認のみ。印刷は絶対に行いません。", foreground="#505050").pack(anchor="w", pady=(2, 16))

        form = ttk.Frame(root)
        form.pack(fill="x")
        self._path_row(form, 0, "スキャン受信フォルダ", self.inbox_value)
        self._path_row(form, 1, "加工画像の保存先", self.output_value)
        ttk.Label(form, text="画像の回転").grid(row=2, column=0, sticky="w", pady=(12, 5))
        ttk.Combobox(form, textvariable=self.rotation_value, values=("0", "90", "180", "270"), state="readonly", width=7).grid(row=2, column=1, sticky="w", padx=4, pady=(12, 5))
        ttk.Label(form, text="度（反時計回り）").grid(row=2, column=2, sticky="w", pady=(12, 5))
        form.columnconfigure(1, weight=1)

        commands = ttk.Frame(root)
        commands.pack(fill="x", pady=(14, 10))
        self.start_button = ttk.Button(commands, text="監視を開始", command=self._start)
        self.start_button.pack(side="left", padx=(0, 10))
        self.stop_button = ttk.Button(commands, text="停止", command=self._stop, state="disabled")
        self.stop_button.pack(side="left")
        self.preview_button = ttk.Button(commands, text="直近のA4画像を開く", command=self._open_preview, state="disabled")
        self.preview_button.pack(side="right")

        status = ttk.Frame(root)
        status.pack(fill="x", pady=(4, 6))
        ttk.Label(status, textvariable=self.status_value, font=("Yu Gothic UI", 10, "bold")).pack(side="left")
        ttk.Label(status, textvariable=self.count_value).pack(side="right")
        ttk.Separator(root).pack(fill="x", pady=(4, 8))
        self.log = tk.Text(root, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        ttk.Label(root, text="新しいJPEGのみ受付。既存ファイルは無視します。Ctrl+Wで終了。", foreground="#666666").pack(anchor="w", pady=(7, 0))
        self.bind("<Control-w>", lambda _e: self._on_close())

    def _path_row(self, parent, row, label, value):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(parent, textvariable=value).grid(row=row, column=1, sticky="ew", padx=(10, 8), pady=(0, 10))
        ttk.Button(parent, text="参照", command=lambda: self._choose_folder(value)).grid(row=row, column=2, sticky="e", pady=(0, 10))

    def _choose_folder(self, value):
        chosen = filedialog.askdirectory(parent=self)
        if chosen:
            value.set(chosen)

    def _load_settings(self):
        try:
            settings = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.inbox_value.set(str(settings.get("inbox", "")))
            self.output_value.set(str(settings.get("output", "")))
            if str(settings.get("rotate", "0")) in {"0", "90", "180", "270"}:
                self.rotation_value.set(str(settings["rotate"]))
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save_settings(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps({"inbox": self.inbox_value.get(),
                                                     "output": self.output_value.get(),
                                                     "rotate": self.rotation_value.get()},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            self._log("設定の保存に失敗しました。")

    def _log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            inbox = Path(self.inbox_value.get()).expanduser().resolve(strict=True)
            output = Path(self.output_value.get()).expanduser().resolve()
            if not inbox.is_dir() or not _paths_safe(inbox, output):
                raise ValueError("受信フォルダと保存先は別々の場所を指定してください。")
            if not self.inbox_value.get().strip() or not self.output_value.get().strip():
                raise ValueError("2つのフォルダを指定してください。")
            rotation = int(self.rotation_value.get())
            if rotation not in (0, 90, 180, 270):
                raise ValueError("回転角が正しくありません。")
            output.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("開始できません", str(exc), parent=self)
            return
        self._save_settings()
        self.stop_event = threading.Event()
        self.last_preview = None
        self.preview_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_value.set("監視を開始しています（印刷OFF）")
        self.worker = threading.Thread(target=self._run_monitor, args=(inbox, output, rotation, self.stop_event), daemon=True)
        self.worker.start()

    def _run_monitor(self, inbox: Path, output: Path, rotation: int, stop: threading.Event):
        guard = None
        store = None
        try:
            guard = SingleInstance(output / ".monitor.lock")
            store = JobStore(output / "jobs.sqlite3")
            pipeline = ScanPipeline(store, output, armed=False, rotate=rotation, stop=stop)
            monitor = InboxMonitor(inbox, pipeline)
            self.notifications.put(("status", "監視中・印刷OFF"))
            while not stop.is_set():
                for name, outcome in monitor.poll_once():
                    self.notifications.put(("log", f"{name}: {outcome}"))
                    for record in reversed(store.rows()):
                        if Path(record["source_path"]).name == name:
                            preview = record.get("preview_path", "")
                            if preview and Path(preview).is_file():
                                self.notifications.put(("preview", preview))
                            break
                stop.wait(.8)
        except Exception as exc:
            self.notifications.put(("log", f"監視エラー: {type(exc).__name__} / {exc}"))
        finally:
            if store is not None:
                store.close()
            if guard is not None:
                guard.close()
            self.notifications.put(("stopped", "停止中（印刷OFF）"))

    def _drain_notifications(self):
        try:
            while True:
                event, payload = self.notifications.get_nowait()
                if event == "status":
                    self.status_value.set(payload)
                elif event == "log":
                    self.received += 1
                    self.count_value.set(f"受信結果：{self.received}件")
                    self._log(payload)
                elif event == "preview":
                    self.last_preview = Path(payload)
                    self.preview_button.configure(state="normal")
                elif event == "stopped":
                    self.status_value.set(payload)
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
        except queue.Empty:
            pass
        if self.stopping_for_exit:
            if not self.worker or not self.worker.is_alive():
                self.destroy()
                return
        self.after(200, self._drain_notifications)

    def _stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status_value.set("停止処理中（印刷OFF）")

    def _open_preview(self):
        if not self.last_preview or not self.last_preview.is_file():
            return
        try:
            os.startfile(str(self.last_preview))  # Windows default image viewer, not print.
        except OSError as exc:
            messagebox.showerror("表示できません", str(exc), parent=self)

    def _on_close(self):
        self.stopping_for_exit = True
        self.stop_event.set()
        self.status_value.set("終了処理中")
        if not self.worker or not self.worker.is_alive():
            self.destroy()


def main() -> None:
    PreviewApp().mainloop()


if __name__ == "__main__":
    main()
