# Copyright (c) 2026 FireSwordss. Free for non-commercial use.
"""SiftByExif - Tkinter GUI application."""

import os, sys, json, threading, shutil, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import defaultdict
from PIL import Image

from .brands import BRANDS
from .scanner import detect_recovery, scan_folder
from .renamer import rename_in_folder
from .gps_sorter import extract_gps, sort_by_gps, move_to_city_folders


class NefRecoveryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SiftByExif")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        # State
        self.target_dir = tk.StringVar()
        self.scan_mode = tk.StringVar(value="recovery")
        self.brand_vars = {}
        self.do_detect = tk.BooleanVar(value=True)
        self.do_rename = tk.BooleanVar(value=True)
        self.do_gps = tk.BooleanVar(value=True)
        self.do_scan = tk.BooleanVar(value=True)
        self.use_online_geo = tk.BooleanVar(value=False)
        self._cancel_flag = False  # Thread-safe cancel flag

        # Scan results (before execution)
        self.report_data = []  # [(filepath, check, result, action), ...]
        self.actions_pending = []  # action descriptions

        self._build_ui()

    # ============================================================
    # UI Construction
    # ============================================================

    def _build_ui(self):
        # Top: directory selector
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)
        ttk.Label(top, text="目录:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.target_dir, width=60).pack(
            side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(top, text="浏览...", command=self._browse_dir).pack(side=tk.LEFT)

        # Middle: left panel (features + brands), right panel (report)
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        left = ttk.Frame(main, width=320)
        right = ttk.Frame(main)
        main.add(left, weight=0)
        main.add(right, weight=1)

        self._build_features(left)
        self._build_brands(left)
        self._build_report(right)

        # Bottom: progress + buttons
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill=tk.X)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            bottom, variable=self.progress_var, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))
        self.progress_label = ttk.Label(bottom, text="就绪")
        self.progress_label.pack(anchor=tk.W)

        btn_frame = ttk.Frame(bottom)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        self.scan_btn = ttk.Button(btn_frame, text="开始扫描",
                                   command=self._start_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=4)
        self.confirm_btn = ttk.Button(btn_frame, text="确认并执行",
                                      command=self._confirm_execute,
                                      state=tk.DISABLED)
        self.confirm_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="取消", command=self._cancel).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="导出报告",
                   command=self._export_report).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="帮助",
                   command=self._show_help).pack(side=tk.RIGHT, padx=4)

    def _build_features(self, parent):
        f = ttk.LabelFrame(parent, text="功能选择", padding=6)
        f.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(f, text="相机照片检测", variable=self.do_detect).pack(
            anchor=tk.W)
        mode_f = ttk.Frame(f)
        mode_f.pack(anchor=tk.W, padx=(20, 0), pady=(0, 4))
        ttk.Radiobutton(mode_f, text="快速模式", variable=self.scan_mode,
                        value="fast").pack(anchor=tk.W)
        ttk.Radiobutton(mode_f, text="恢复模式", variable=self.scan_mode,
                        value="recovery").pack(anchor=tk.W)
        ttk.Checkbutton(f, text="恢复原始文件名", variable=self.do_rename).pack(
            anchor=tk.W)
        ttk.Checkbutton(f, text="GPS聚类排序", variable=self.do_gps).pack(
            anchor=tk.W)
        gps_f = ttk.Frame(f)
        gps_f.pack(anchor=tk.W, padx=(20, 0))
        ttk.Checkbutton(gps_f, text="使用在线地理编码 (Nominatim)",
                        variable=self.use_online_geo).pack(anchor=tk.W)
        ttk.Checkbutton(f, text="损坏扫描", variable=self.do_scan).pack(
            anchor=tk.W)

    def _build_brands(self, parent):
        f = ttk.LabelFrame(parent, text="品牌筛选", padding=6)
        f.pack(fill=tk.BOTH, expand=True)

        btn_f = ttk.Frame(f)
        btn_f.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(btn_f, text="全选", command=self._select_all_brands).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="清空", command=self._clear_brands).pack(
            side=tk.LEFT, padx=2)

        # Scrollable brand list
        canvas = tk.Canvas(f, height=200, highlightthickness=0)
        scrollbar = ttk.Scrollbar(f, orient=tk.VERTICAL, command=canvas.yview)
        brand_frame = ttk.Frame(canvas)
        brand_frame.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=brand_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        for brand_name in BRANDS:
            var = tk.BooleanVar(value=True)
            self.brand_vars[brand_name] = var
            ttk.Checkbutton(brand_frame, text=brand_name, variable=var).pack(
                anchor=tk.W)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_report(self, parent):
        f = ttk.LabelFrame(parent, text="扫描报告", padding=6)
        f.pack(fill=tk.BOTH, expand=True)

        # Treeview with scrollbars
        cols = ("文件", "目录", "检查项", "结果", "操作")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=15)
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("文件", width=180)
        self.tree.column("目录", width=150)
        self.tree.column("检查项", width=140)
        self.tree.column("结果", width=120)
        self.tree.column("操作", width=200)

        vsb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(f, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        f.grid_rowconfigure(0, weight=1)
        f.grid_columnconfigure(0, weight=1)

    # ============================================================
    # Brand selection
    # ============================================================

    def _select_all_brands(self):
        for var in self.brand_vars.values():
            var.set(True)

    def _clear_brands(self):
        for var in self.brand_vars.values():
            var.set(False)

    def _get_selected_brands(self):
        return [name for name, var in self.brand_vars.items() if var.get()]

    # ============================================================
    # Directory
    # ============================================================

    def _browse_dir(self):
        d = filedialog.askdirectory(title="选择照片目录")
        if d:
            self.target_dir.set(d)

    # ============================================================
    # Scan workflow
    # ============================================================

    def _start_scan(self):
        d = self.target_dir.get().strip()
        if not d or not os.path.isdir(d):
            self._show_error("请先选择一个有效的目录。")
            return

        self._cancel_flag = False
        self.scan_btn.configure(state=tk.DISABLED)
        self.confirm_btn.configure(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.report_data = []
        self.actions_pending = []
        self.progress_var.set(0)
        self.progress_label.configure(text="扫描中...")

        t = threading.Thread(target=self._run_scan, args=(d,), daemon=True)
        t.start()

    def _run_scan(self, dir_path):
        try:
            report = []
            actions = []

            selected_brands = self._get_selected_brands()
            do_detect = self.do_detect.get()
            do_rename = self.do_rename.get()
            do_gps = self.do_gps.get()
            do_scan = self.do_scan.get()
            use_online = self.use_online_geo.get()

            # Collect all files
            all_files = self._collect_files(dir_path)

            # Step 1: Camera detection
            if do_detect:
                self._set_progress_label("检测相机照片...")
                detected_files = {}
                for i, fp in enumerate(all_files):
                    brand = detect_recovery(fp, selected_brands)
                    detected_files[fp] = brand
                    self._update_progress(i, len(all_files))
                self._update_progress(len(all_files), len(all_files))

                # Report detected/not detected
                for fp, brand in detected_files.items():
                    rel = self._rel_path(fp, dir_path)
                    if brand:
                        report.append((os.path.basename(fp), rel,
                                       "品牌识别", brand, ""))
                    else:
                        report.append((os.path.basename(fp), rel,
                                       "品牌识别", "非相机照片", "跳过"))

                # Filter to only detected files for subsequent steps
                camera_files = [fp for fp, b in detected_files.items() if b]
                if not camera_files:
                    self._finish_scan(report, actions,
                                      "未检测到相机照片，扫描完成。")
                    return
            else:
                camera_files = list(all_files)

            if self._cancel_flag:
                return self._finish_cancel()

            # Step 2: Rename
            if do_rename and camera_files:
                self._set_progress_label("恢复原始文件名...")
                # Group files by folder for batch rename
                by_folder = defaultdict(list)
                for fp in camera_files:
                    by_folder[os.path.dirname(fp)].append(fp)

                total_folders = len(by_folder)
                for fi, (folder, files) in enumerate(by_folder.items()):
                    rel = self._rel_path(folder, dir_path)
                    renamed, skipped, errs = rename_in_folder(
                        folder, progress_cb=None)

                    if renamed > 0:
                        report.append(("—", rel, "文件名恢复",
                                       f"{renamed} 个已重命名", ""))
                    if skipped > 0:
                        report.append(("—", rel, "文件名恢复",
                                       f"{skipped} 个已跳过", ""))
                    for fname, err in errs:
                        report.append((fname, rel, "文件名恢复",
                                       f"错误: {err}", "跳过"))

                    self._update_progress(fi, total_folders)
                self._update_progress(total_folders, total_folders)

                # Refresh camera_files paths after rename
                camera_files = self._collect_files(dir_path)
                if do_detect:
                    camera_files = [fp for fp in camera_files
                                    if detect_recovery(fp, selected_brands)]

            if self._cancel_flag:
                return self._finish_cancel()

            # Step 3: GPS sort
            if do_gps and camera_files:
                self._set_progress_label("GPS提取与聚类...")
                gps_data = []
                for i, fp in enumerate(camera_files):
                    coords = extract_gps(fp)
                    if coords:
                        gps_data.append((fp, coords[0], coords[1]))
                    else:
                        gps_data.append((fp, None, None))
                    self._update_progress(i, len(camera_files))
                self._update_progress(len(camera_files), len(camera_files))

                city_groups = sort_by_gps(gps_data, use_online=use_online)

                actions.append(("GPS排序", city_groups, dir_path))

                # Report
                for city, files in sorted(
                    city_groups.items(),
                    key=lambda x: (x[0] is None, str(x[0] or ''))
                ):
                    cn = city if city else "无GPS信息"
                    if cn == "其他":
                        cn += f" ({len(files)} 个未聚类)"
                    report.append(("—", cn, "GPS聚类",
                                   f"{len(files)} 个文件", f"移入 {cn}/"))

            if self._cancel_flag:
                return self._finish_cancel()

            # Step 4: Corruption scan
            if do_scan:
                self._set_progress_label("损坏扫描...")
                leaf_folders = _find_leaf_folders(dir_path)
                all_results = {}
                total_folders = len(leaf_folders)
                for fi, folder in enumerate(leaf_folders):
                    rel = self._rel_path(folder, dir_path)
                    self._set_progress_label(f"损坏扫描: {rel} ({fi+1}/{total_folders})")
                    results = scan_folder(folder)
                    all_results[folder] = results
                    for fname, issues in results:
                        for check, severity, msg in issues:
                            report.append((fname, rel, check,
                                           f"[{severity}] {msg}",
                                           "移入疑似损坏/"))
                        if issues:
                            actions.append(("隔离损坏",
                                            (folder, fname, issues),
                                            dir_path))
                    self._update_progress(fi + 1, total_folders)

                # Summary
                total_r = sum(len(v) for v in all_results.values())
                clean = sum(1 for v in all_results.values()
                            for _, issues in v if not issues)
                flagged = total_r - clean
                report.append(("—", "—", "损坏扫描完成",
                               f"干净: {clean}, 疑似损坏: {flagged}", ""))

            self._finish_scan(report, actions, "扫描完成，请检查报告后确认执行。")

        except Exception as e:
            self._show_error(f"扫描出错: {e}", is_thread=True)

    def _collect_files(self, dir_path):
        """Walk dir_path and return list of all file paths."""
        files = []
        for dirpath, _, filenames in os.walk(dir_path):
            if '疑似损坏' in dirpath:
                continue
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                if os.path.isfile(fp):
                    files.append(fp)
        return files

    def _rel_path(self, full_path, base):
        try:
            return os.path.relpath(full_path, base)
        except Exception:
            return full_path

    def _update_progress(self, current, total):
        if total > 0:
            self.root.after(0, lambda: self.progress_var.set(
                (current / total) * 100))

    def _set_progress_label(self, text):
        self.root.after(0, lambda: self.progress_label.configure(text=text))

    def _finish_scan(self, report, actions, msg):
        def _do():
            self.report_data = report
            self.actions_pending = actions
            self.tree.delete(*self.tree.get_children())
            for i, row in enumerate(report):
                self.tree.insert("", tk.END, values=row)
            self.progress_label.configure(text=msg)
            self.scan_btn.configure(state=tk.NORMAL)
            if actions:
                self.confirm_btn.configure(state=tk.NORMAL)
        self.root.after(0, _do)

    # ============================================================
    # Execute confirmed actions
    # ============================================================

    def _confirm_execute(self):
        if not self.actions_pending:
            return

        if not messagebox.askyesno("确认", "将执行以下操作：\n\n" +
                                   self._summarize_actions() +
                                   "\n\n确认继续？"):
            return

        self.confirm_btn.configure(state=tk.DISABLED)
        self.progress_label.configure(text="执行中...")
        t = threading.Thread(target=self._execute_actions, daemon=True)
        t.start()

    def _summarize_actions(self):
        lines = []
        for action in self.actions_pending:
            atype = action[0]
            if atype == "GPS排序":
                _, groups, _ = action
                for city, files in groups.items():
                    cn = city if city else "无GPS信息"
                    lines.append(f"  · 移入 {cn}/ : {len(files)} 个文件")
            elif atype == "隔离损坏":
                lines.append(f"  · 移入疑似损坏/ : 1 个文件")
        return "\n".join(lines[:20])

    def _execute_actions(self):
        try:
            total = len(self.actions_pending)
            for i, action in enumerate(self.actions_pending):
                atype = action[0]
                if atype == "GPS排序":
                    _, groups, root_dir = action
                    move_to_city_folders(root_dir, groups)
                elif atype == "隔离损坏":
                    _, (folder, fname, issues), root_dir = action
                    # Move to quarantine within parent
                    rel = self._rel_path(folder, root_dir)
                    parts = rel.replace('\\', '/').split('/')
                    parent = parts[0]
                    sub = '/'.join(parts[1:]) if len(parts) > 1 else ''
                    dst_dir = os.path.join(root_dir, parent, "疑似损坏", sub)
                    os.makedirs(dst_dir, exist_ok=True)
                    src = os.path.join(folder, fname)
                    dst = os.path.join(dst_dir, fname)
                    if os.path.exists(src):
                        shutil.move(src, dst)

                self._update_progress(i + 1, total)

            self._set_progress_label("执行完成。")
            self.progress_var.set(0)
            self.confirm_btn.configure(state=tk.DISABLED)
            self.actions_pending = []

        except Exception as e:
            self._show_error(f"执行出错: {e}", is_thread=True)

    # ============================================================
    # Helpers
    # ============================================================

    def _cancel(self):
        self._cancel_flag = True
        self.progress_label.configure(text="正在取消...")
        self.confirm_btn.configure(state=tk.DISABLED)

    def _finish_cancel(self):
        def _do():
            self.progress_var.set(0)
            self.progress_label.configure(text="已取消")
            self.scan_btn.configure(state=tk.NORMAL)
            self.confirm_btn.configure(state=tk.DISABLED)
        self.root.after(0, _do)

    def _export_report(self):
        if not self.report_data:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        import csv
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["文件", "目录", "检查项", "结果", "操作"])
            for row in self.report_data:
                writer.writerow(row)
        self.progress_label.configure(text=f"报告已导出: {path}")

    def _show_help(self):
        help_text = (
            "SiftByExif - 使用说明\n\n"
            "功能\n"
            "   相机照片检测 - 从混合文件中筛出相机照片，按品牌归类\n"
            "   恢复原始文件名 - 从 Nikon MakerNote 恢复 DSC_XXXX.NEF\n"
            "   GPS聚类排序 - 按拍摄位置分城市文件夹\n"
            "   损坏扫描 - 检查 NEF 结构、EXIF、嵌入JPEG\n\n"
            "步骤\n"
            "   1) 选择目录  2) 勾选功能  3) 开始扫描\n"
            "   4) 检查报告  5) 确认并执行\n\n"
            "损坏扫描说明\n"
            "   能检测: 文件不可读、TIFF结构损坏、嵌入JPEG损坏、EXIF缺失\n"
            "   不能检测: 像素级静默损坏、RAW Bayer数据损坏\n"
            "   已知误报: 过曝/欠曝照片因文件大小异常可能被标记(MEDIUM)\n"
            "             长曝光照片文件较大可能超出统计基线\n"
            "   被标记文件移入各父目录下的\"疑似损坏/\"，不删除\n\n"
            "依赖: ExifTool (需单独安装)\n"
            "许可: Copyright (c) 2026 FireSwordss. 非商用免费"
        )
        win = tk.Toplevel(self.root)
        win.title("SiftByExif - 帮助")
        win.geometry("600x500")
        txt = tk.Text(win, wrap=tk.WORD, padx=12, pady=12,
                      font=("Microsoft YaHei UI", 10))
        txt.insert("1.0", help_text)
        txt.configure(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)

    def _show_error(self, msg, is_thread=False):
        """Log error silently to status bar — no popup during scan."""
        if is_thread:
            self.root.after(0, lambda: self._show_error(msg, False))
        else:
            self.progress_label.configure(text=f"[错误] {msg}")
            self.scan_btn.configure(state=tk.NORMAL)
            self.scan_btn.configure(state=tk.NORMAL)


def _find_leaf_folders(root):
    """Find all folders containing NEF files, for batch-statistics scanning."""
    folders = []
    for dirpath, dirnames, filenames in os.walk(root):
        if '疑似损坏' in dirpath:
            continue
        if any(f.upper().endswith('.NEF') for f in filenames):
            folders.append(dirpath)
    return folders


def main():
    root = tk.Tk()
    app = NefRecoveryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
