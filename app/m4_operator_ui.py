"""APP-033 operator desktop. No printing is authorized at startup.

A manual physical trial print plus an explicit confirmation in *this process*
are required before the auto-print monitor can be armed. No credentials or
remote services. Hardware validation remains a separate user-owned step.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from m2_monitor import InboxMonitor, JobStore, ScanPipeline, SingleInstance, _paths_safe
from m4_print_gate import GateError, PrintGate


def preview_history(output: Path, limit: int = 75) -> list[dict]:
    """Read-only access: do not auto-recover, requeue or submit old jobs."""
    db = output / "jobs.sqlite3"
    if not db.is_file():
        return []
    connection = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(x) for x in connection.execute(
            "SELECT id, source_path, state, message, preview_path, spool_id, updated_at "
            "FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,)
        )]
    finally:
        connection.close()


class OperatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("黒カット印刷 | APP-033")
        self.geometry("740x660")
        self.minsize(630, 555)
        self.worker: threading.Thread | None = None
        self.manual_worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.notifications: queue.Queue[tuple[str, object]] = queue.Queue()
        self.gate = PrintGate()
        self.rows_by_id: dict[str, dict] = {}
        self.pending_exit = False
        self.config_file = Path(os.environ.get("APPDATA") or str(Path.home())) / "BlackCutPrint" / "settings.json"
        self.inbox = tk.StringVar()
        self.output = tk.StringVar()
        self.rotation = tk.StringVar(value="0")
        self.source_dpi = tk.StringVar(value="300")
        self.printer = tk.StringVar()
        self.status = tk.StringVar(value="停止中・自動印刷OFF")
        self.permission = tk.StringVar(value="自動印刷：OFF（手動試し刷り未確認）")
        self._load_settings()
        self._draw()
        self.printer.trace_add("write", self._printer_changed)
        self.after(200, self._events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _draw(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="黒カット印刷", font=("Yu Gothic UI", 17, "bold")).pack(anchor="w")
        ttk.Label(container, text="新規スキャンを自動加工。手動の紙検収が終わるまで無人印刷はOFFです。",
                  foreground="#555555").pack(anchor="w", pady=(2, 12))
        fields = ttk.Frame(container)
        fields.pack(fill="x")
        fields.columnconfigure(1, weight=1)
        self._folder_field(fields, 0, "スキャン受信", self.inbox)
        self._folder_field(fields, 1, "加工画像保存", self.output)
        ttk.Label(fields, text="印刷先").grid(row=2, column=0, sticky="w", pady=5)
        self.printer_combo = ttk.Combobox(fields, textvariable=self.printer, state="readonly")
        self.printer_combo.grid(row=2, column=1, sticky="ew", padx=8, pady=5)
        self.printer_reload = ttk.Button(fields, text="一覧更新", command=self._list_printers)
        self.printer_reload.grid(row=2, column=2, sticky="e", pady=5)
        ttk.Label(fields, text="固定回転").grid(row=3, column=0, sticky="w", pady=5)
        options = ttk.Frame(fields)
        options.grid(row=3, column=1, sticky="w", padx=8, pady=5)
        self.rotation_combo = ttk.Combobox(options, textvariable=self.rotation,
                                           values=("0", "90", "180", "270"), width=6, state="readonly")
        self.rotation_combo.pack(side="left")
        ttk.Label(options, text="度（反時計回り）  /  読取DPI：").pack(side="left", padx=8)
        self.dpi_combo = ttk.Combobox(options, textvariable=self.source_dpi,
                                     values=("150", "200", "300", "400", "600"), state="readonly", width=6)
        self.dpi_combo.pack(side="left")
        ttk.Separator(container).pack(fill="x", pady=(10, 10))

        controls = ttk.Frame(container)
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="監視を開始", command=self._start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="停止", command=self._stop, state="disabled")
        self.stop_button.pack(side="left")
        self.arm_button = ttk.Button(controls, text="自動印刷を許可", command=self._arm,
                                     state="disabled")
        self.arm_button.pack(side="right")
        self.disarm_button = ttk.Button(controls, text="印刷OFF", command=self._disarm,
                                        state="disabled")
        self.disarm_button.pack(side="right", padx=8)

        ttk.Label(container, textvariable=self.status, font=("Yu Gothic UI", 10, "bold")).pack(anchor="w", pady=(12, 2))
        ttk.Label(container, textvariable=self.permission, foreground="#555555").pack(anchor="w", pady=(0, 8))

        record_controls = ttk.Frame(container)
        record_controls.pack(fill="x", pady=(4, 4))
        ttk.Label(record_controls, text="最近の処理履歴").pack(side="left")
        self.history_refresh = ttk.Button(record_controls, text="更新", command=self._refresh_history)
        self.history_refresh.pack(side="right")
        columns = ("file", "state", "time")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=7, selectmode="browse")
        self.tree.heading("file", text="原稿ファイル")
        self.tree.heading("state", text="状態")
        self.tree.heading("time", text="更新日時")
        self.tree.column("file", width=300, stretch=True)
        self.tree.column("state", width=140, stretch=False)
        self.tree.column("time", width=175, stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(8, 8))
        ttk.Button(actions, text="選択したプレビューを開く", command=self._open_selected).pack(side="left")
        self.manual_button = ttk.Button(actions, text="選択した原稿を1枚試し刷り",
                                         command=self._manual_test)
        self.manual_button.pack(side="left", padx=8)
        self.verify_button = ttk.Button(actions, text="紙の結果を確認", command=self._verify_paper,
                                         state="disabled")
        self.verify_button.pack(side="right")
        ttk.Separator(container).pack(fill="x", pady=5)
        self.log = tk.Text(container, height=5, state="disabled", font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=False)
        ttk.Label(container, text="再起動後の自動印刷許可は無効。印刷完了・紙排出は別々に確認します。",
                  foreground="#666666").pack(anchor="w", pady=(9, 0))
        self._refresh_history()

    def _folder_field(self, parent, row, label, value):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=value).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="参照", command=lambda: self._browse(value)).grid(row=row, column=2, sticky="e", pady=5)

    def _browse(self, value):
        folder = filedialog.askdirectory(parent=self)
        if folder:
            value.set(folder)

    def _load_settings(self):
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            self.inbox.set(str(data.get("inbox", "")))
            self.output.set(str(data.get("output", "")))
            if str(data.get("rotation", "0")) in {"0", "90", "180", "270"}:
                self.rotation.set(str(data["rotation"]))
            if str(data.get("source_dpi", "300")) in {"150", "200", "300", "400", "600"}:
                self.source_dpi.set(str(data["source_dpi"]))
            # Never restore print permissions or selected queue from disk.
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _save_settings(self):
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps({
                "inbox": self.inbox.get(), "output": self.output.get(),
                "rotation": self.rotation.get(), "source_dpi": self.source_dpi.get(),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            self._log("設定を保存できませんでした。")

    def _printer_changed(self, *_):
        # If the queue changes while a worker is active, forbid further sends.
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
        self.gate.set_printer(self.printer.get())
        self._sync_gate_controls()

    def _sync_gate_controls(self):
        armed = self.gate.will_submit(self.printer.get())
        self.permission.set("自動印刷：ON（監視中の新規原稿のみ）" if armed
                            else "自動印刷：OFF（今回の起動での手動印刷確認が必要）")
        idle = not (self.worker and self.worker.is_alive())
        available = self.gate.verified_printer == self.printer.get() and idle
        self.arm_button.configure(state="normal" if available and not armed else "disabled")
        self.disarm_button.configure(state="normal" if armed and idle else "disabled")
        busy = bool(self.manual_worker and self.manual_worker.is_alive())
        self.manual_button.configure(state="normal" if idle and not armed and
                                     not busy and not self.gate.waiting_for_paper and
                                     not self.gate.pending_printer else "disabled")
        self.verify_button.configure(state="normal" if self.gate.waiting_for_paper and idle else "disabled")
        self.printer_combo.configure(state="readonly" if idle and not busy and
                                     not self.gate.waiting_for_paper else "disabled")

    def _list_printers(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            from windows_print import list_printers
            available = list_printers()
        except Exception as exc:
            messagebox.showerror("一覧取得失敗", str(exc), parent=self)
            return
        self.printer_combo.configure(values=available)
        if self.printer.get() not in available:
            self.printer.set("")
        self._log(f"印刷キュー {len(available)}件を検出。")

    def _log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _validated_paths(self):
        if not self.inbox.get().strip() or not self.output.get().strip():
            raise ValueError("受信・保存フォルダの両方を指定してください。")
        incoming = Path(self.inbox.get()).expanduser().resolve(strict=True)
        output = Path(self.output.get()).expanduser().resolve()
        if not incoming.is_dir() or not _paths_safe(incoming, output):
            raise ValueError("受信フォルダと結果フォルダは重複しない場所を指定してください。")
        output.mkdir(parents=True, exist_ok=True)
        return incoming, output

    def _refresh_history(self):
        if not self.output.get().strip():
            return
        try:
            root = Path(self.output.get()).expanduser().resolve()
            rows = preview_history(root)
        except (ValueError, OSError, sqlite3.Error):
            rows = []
        self.rows_by_id = {row["id"]: row for row in rows}
        selection = self.tree.selection()
        previous = selection[0] if selection else None
        for child in self.tree.get_children():
            self.tree.delete(child)
        for row in rows:
            name = Path(row["source_path"]).name
            self.tree.insert("", "end", iid=row["id"],
                             values=(name, row["state"], row["updated_at"]))
        if previous in self.rows_by_id:
            self.tree.selection_set(previous)

    def _selected_row(self):
        choice = self.tree.selection()
        return self.rows_by_id.get(choice[0]) if choice else None

    def _open_selected(self):
        record = self._selected_row()
        if not record:
            return
        preview = Path(record["preview_path"]) if record["preview_path"] else None
        if not preview or not preview.is_file():
            messagebox.showinfo("プレビューなし", "このジョブには印刷用プレビューがありません。", parent=self)
            return
        try:
            if os.name != "nt":
                raise OSError("画像ビューアー起動はWindowsのみ")
            os.startfile(str(preview))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("開けません", str(exc), parent=self)

    def _manual_test(self):
        if self.worker and self.worker.is_alive():
            messagebox.showerror("監視中", "監視を停止してから試し刷りしてください。", parent=self)
            return
        record = self._selected_row()
        printer = self.printer.get()
        if not record or record["state"] != "READY_REVIEW":
            messagebox.showinfo("原稿を選択", "印刷せず加工したREADY_REVIEWの原稿を選択してください。", parent=self)
            return
        preview = Path(record["preview_path"]) if record["preview_path"] else Path("")
        try:
            self.gate.begin_manual_test(printer, preview)
        except GateError as exc:
            messagebox.showerror("試し刷り不可", str(exc), parent=self)
            return
        ok = messagebox.askyesno(
            "実際に1枚印刷します",
            f"次のプリンターにA4・片面・白黒・1部を送信します。\n{printer}\n\n"
            "プリンターの前に用紙があることを確認してください。送信しますか？",
            parent=self,
        )
        if not ok:
            self.gate.manual_failed()
            self._sync_gate_controls()
            return
        self.manual_button.configure(state="disabled")
        self.printer_combo.configure(state="disabled")
        self._log("手動試し刷りを送信しています（同じジョブを自動で再送しません）。")
        self.manual_worker = threading.Thread(
            target=self._send_manual, args=(preview, printer), daemon=True
        )
        self.manual_worker.start()

    def _send_manual(self, preview, printer):
        try:
            from windows_print import submit_a4
            ident = submit_a4(preview, printer)
            self.notifications.put(("manual_ok", ident))
        except BaseException as exc:
            self.notifications.put(("manual_error", f"{type(exc).__name__}: {exc}"))

    def _verify_paper(self):
        if not self.gate.waiting_for_paper:
            return
        yes = messagebox.askyesno(
            "手動試し刷りの確認",
            "実際に用紙が排出され、A4・片面・ちょうど1部で、"
            "文字・図版・余白・向き・倍率に問題がないことを確認しましたか？\n\n"
            "不確かな場合は「いいえ」を選んでください。",
            parent=self,
        )
        self.gate.confirm_paper(paper_present=yes, exactly_one=yes, image_ok=yes)
        self._log("実紙の目視確認：合格。自動印刷を許可できます。" if yes else
                  "実紙の検証未合格：自動印刷は禁止のままです。")
        self._sync_gate_controls()

    def _arm(self):
        if self.worker and self.worker.is_alive():
            return
        printer = self.printer.get()
        if not messagebox.askyesno(
            "無人印刷ONの最終確認",
            f"手動試し刷り済みの {printer} に新規スキャンが自動送信されます。\n"
            "監視開始前の原稿は処理しません。\n\n自動印刷を許可しますか？",
            parent=self,
        ):
            return
        try:
            from windows_print import list_printers
            if printer not in list_printers():
                raise GateError("印刷先が見つかりません")
            self.gate.arm(printer, explicit_confirmation=True)
        except Exception as exc:
            messagebox.showerror("自動印刷許可不可", str(exc), parent=self)
            return
        self._log("自動印刷許可ON。次に監視を開始すると新規スキャンだけを印刷します。")
        self._sync_gate_controls()

    def _disarm(self):
        if self.worker and self.worker.is_alive():
            self._stop()
            return
        self.gate.disarm()
        self._log("自動印刷をOFFにしました。")
        self._sync_gate_controls()

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            inbox, output = self._validated_paths()
            rotation, dpi = int(self.rotation.get()), float(self.source_dpi.get())
            if rotation not in (0, 90, 180, 270) or not 72 <= dpi <= 1200:
                raise ValueError("回転か読取解像度の指定が無効です")
            printer = self.printer.get()
            armed = self.gate.will_submit(printer)
            if armed:
                from windows_print import list_printers
                if printer not in list_printers():
                    raise ValueError("印刷先を見つけられません。監視開始は中止しました。")
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("開始できません", str(exc), parent=self)
            return
        self._save_settings()
        self.stop_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.manual_button.configure(state="disabled")
        self.printer_combo.configure(state="disabled")
        self.arm_button.configure(state="disabled")
        self.disarm_button.configure(state="disabled")
        self.status.set("監視を開始しています" + ("（自動印刷ON）" if armed else "（印刷OFF）"))
        self.worker = threading.Thread(
            target=self._run_monitor,
            args=(inbox, output, rotation, dpi, printer, armed, self.stop_event),
            daemon=True,
        )
        self.worker.start()

    def _run_monitor(self, inbox, output, rotation, dpi, printer, armed, stop):
        lock = None
        store = None
        try:
            lock = SingleInstance(output / ".monitor.lock")
            store = JobStore(output / "jobs.sqlite3")
            sender = None
            if armed:
                from windows_print import submit_a4
                sender = submit_a4
            pipeline = ScanPipeline(store, output, printer=printer, armed=armed,
                                    sender=sender, source_dpi=dpi, rotate=rotation, stop=stop)
            monitor = InboxMonitor(inbox, pipeline)
            self.notifications.put(("status", "監視中（印刷ON）" if armed else "監視中（印刷OFF）"))
            while not stop.is_set():
                for name, status in monitor.poll_once():
                    self.notifications.put(("scan", (name, status)))
                stop.wait(0.8)
        except Exception as exc:
            self.notifications.put(("monitor_error", f"{type(exc).__name__}: {exc}"))
        finally:
            if store:
                store.close()
            if lock:
                lock.close()
            self.notifications.put(("stopped", None))

    def _stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("安全停止中：現在の処理を終了しています")

    def _events(self):
        try:
            while True:
                typ, value = self.notifications.get_nowait()
                if typ == "status":
                    self.status.set(str(value))
                elif typ == "scan":
                    name, result = value
                    self._log(f"{name}: {result}")
                    self._refresh_history()
                elif typ == "monitor_error":
                    self._log("監視エラー： " + str(value))
                    self.gate.disarm()
                elif typ == "stopped":
                    self.status.set("停止中・自動印刷" + ("ON" if self.gate.armed else "OFF"))
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self._refresh_history()
                elif typ == "manual_ok":
                    try:
                        self.gate.manual_submitted()
                        self._log(f"手動ジョブをWindowsへ送信済み（ID={value}）。排紙は未確認です。")
                    except GateError:
                        self.gate.manual_failed()
                        self._log("印刷中に条件が変更されたため、実紙確認を無効化しました。")
                    self._refresh_history()
                elif typ == "manual_error":
                    self.gate.manual_failed()
                    self._log("送信結果が不明。自動再送は禁止：" + str(value))
                self._sync_gate_controls()
        except queue.Empty:
            pass
        if self.pending_exit and not (self.worker and self.worker.is_alive()) \
                and not (self.manual_worker and self.manual_worker.is_alive()):
            self.destroy()
            return
        self.after(200, self._events)

    def _close(self):
        self.pending_exit = True
        self.gate.disarm()
        self.stop_event.set()
        if not (self.worker and self.worker.is_alive()) \
                and not (self.manual_worker and self.manual_worker.is_alive()):
            self.destroy()
        else:
            self.status.set("終了処理中：ジョブの再送信はしません")


def main():
    OperatorApp().mainloop()


if __name__ == "__main__":
    main()
