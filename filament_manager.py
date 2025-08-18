"""
filament_manager.py

Single-file Tkinter desktop app "Filament Roll Manager".

Features:
- Persistence to filament_data.json with "active" and "archived" buckets (back-compatible migration).
- Treeview table for active rolls with thumbnail, color, material, remaining grams, description, price/g.
- Add/Edit/Remove (archive)/Use Filament actions.
- Auto-archive when remaining <= 0.
- Price per gram computed at add time.
- Row status icon (green/yellow/red) based on thresholds.
- Stats tab with rolls used, rolls left, total filament used, total rolls tracked, money used.
- Per-roll images stored base64 in JSON; thumbnail column and lightbox display.
- Projects: choose/create project when using filament; tracking per-project totals and export CSV.
- Smart low-stock alerts with per-material thresholds and settings dialog.
- Search/filter bar and sortable columns with in-memory persisted last-sort while app runs.
- Optional charts if matplotlib is installed (bar by material, line over time).
- Robust numeric input validation (accepts ',' or '.').
- Atomic JSON save to temp file then os.replace.
- Uses only stdlib by default; matplotlib is optional and gracefully handled.
- All dialogs non-destructive (cancel won't mutate state).

Author: SOEP
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import json
import os
import sys
import tempfile
import base64
from io import BytesIO
from datetime import datetime, date
import csv
import math
import traceback

HAS_MATPLOTLIB = False
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except Exception:
    HAS_MATPLOTLIB = False


APP_NAME = "Filament Roll Manager"
DATA_FILENAME = "filament_data.json"
PROJECT_CSV = "project_usage.csv"
ICON_SIZE = 12  
THUMBNAIL_SIZE = 48  
DEFAULT_THRESHOLDS = {"default": {"red": 300, "yellow": 1000}}


def safe_float_from_str(s: str, default=0.0) -> float:
    """Convert string with ',' or '.' decimal separators to float. Return default if invalid."""
    if s is None:
        return default
    try:
        s2 = str(s).strip().replace(",", ".")
        if s2 == "":
            return default
        return float(s2)
    except Exception:
        return default

def atomic_write_json(path, data):
    """Write JSON atomically to avoid corruption."""
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="filament_tmp_", suffix=".json", dir=".")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise

def now_iso():
    return datetime.utcnow().isoformat()

def ensure_fields(roll: dict):
    """Migrate/ensure keys exist for a roll (backwards compatibility)."""
    keys = {
        "color": "",
        "material": "",
        "remaining_grams": 0.0,
        "description": "",
        "price_per_gram": 0.0,
        "initial_weight": 0.0,
        "initial_price": 0.0,
        "used_grams": 0.0,
        "photo_b64": None,
        "created_at": now_iso(),
        "id": None,
    }
    for k, v in keys.items():
        if k not in roll:
            roll[k] = v
    # ensure types
    roll["remaining_grams"] = safe_float_from_str(roll["remaining_grams"], 0.0)
    roll["price_per_gram"] = safe_float_from_str(roll["price_per_gram"], 0.0)
    roll["initial_weight"] = safe_float_from_str(roll["initial_weight"], 0.0)
    roll["initial_price"] = safe_float_from_str(roll["initial_price"], 0.0)
    roll["used_grams"] = safe_float_from_str(roll["used_grams"], 0.0)
    if not roll.get("id"):
        roll["id"] = f"r{int(datetime.utcnow().timestamp() * 1000)}"
    return roll

def compute_price_per_gram(initial_price, initial_weight):
    try:
        iw = safe_float_from_str(initial_weight, 0.0)
        ip = safe_float_from_str(initial_price, 0.0)
        return ip / iw if iw > 0 else 0.0
    except Exception:
        return 0.0

def format_money(amount):
    try:
        return f"${amount:,.2f}"
    except Exception:
        return f"${amount}"

def format_grams(g):
    try:
        if g == int(g):
            return f"{int(g)} g"
        return f"{g:.1f} g"
    except Exception:
        return f"{g} g"


class FilamentManagerApp(tk.Tk):
    """Main application window and logic."""
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = int(sw * 0.75)
        h = int(sh * 0.75)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.data = {"active": [], "archived": [], "projects": {}, "thresholds": {}, "usage_events": []}
        self.load_data()

        self.icon_green = self._make_color_icon("green")
        self.icon_yellow = self._make_color_icon("yellow")
        self.icon_red = self._make_color_icon("red")
        self.thumb_cache = {}
        self.row_images = {}

        self.last_sort = ("remaining_grams", False)

        self._create_widgets()

        self.populate_table()
        self.update_stats_tab()
        self.after(500, self.check_low_stock_nonblocking)

    def load_data(self):
        """Load JSON file; migrate missing fields in-memory."""
        if not os.path.exists(DATA_FILENAME):
            self.data = {"active": [], "archived": [], "projects": {}, "thresholds": {}, "usage_events": []}
            return
        try:
            with open(DATA_FILENAME, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)

                for k in ("active", "archived", "projects", "thresholds", "usage_events"):
                    if k not in loaded:
                        loaded[k] = {} if k in ("projects", "thresholds") else []
                loaded["active"] = [ensure_fields(r) for r in loaded.get("active", [])]
                loaded["archived"] = [ensure_fields(r) for r in loaded.get("archived", [])]
                if not isinstance(loaded.get("projects", {}), dict):
                    loaded["projects"] = {}
                if not isinstance(loaded.get("thresholds", {}), dict):
                    loaded["thresholds"] = {}
                if not isinstance(loaded.get("usage_events", []), list):
                    loaded["usage_events"] = []
                self.data = loaded
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load {DATA_FILENAME}:\n{e}")
            self.data = {"active": [], "archived": [], "projects": {}, "thresholds": {}, "usage_events": []}
    def sort_by(self, col, toggle=True, ascending=True):
        """
        Sort the Treeview by the given column.
        col: column name (string)
        toggle: if True, reverse order if column is already sorted
        ascending: initial direction if toggle=False
        """
        tree = self.tree

        data = [(tree.set(k, col), k) for k in tree.get_children("")]

        def try_float(val):
            try:
                return float(val.replace(",", "."))
            except ValueError:
                return val.lower()  

        data = [(try_float(v), k) for v, k in data]

        if toggle:
            current_sort_col = getattr(self, "_sort_col", None)
            current_ascending = getattr(self, "_sort_asc", True)
            if current_sort_col == col:
                ascending = not current_ascending

        data.sort(reverse=not ascending)

        for index, (_, k) in enumerate(data):
            tree.move(k, "", index)

        self._sort_col = col
        self._sort_asc = ascending

    def save_data(self):
        """Save JSON atomically."""
        try:
            atomic_write_json(DATA_FILENAME, self.data)
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save data: {e}")

    def _make_color_icon(self, color):
        """Create small square PhotoImage of given color."""
        img = tk.PhotoImage(width=ICON_SIZE, height=ICON_SIZE)
        for x in range(ICON_SIZE):
            for y in range(ICON_SIZE):
                img.put(color, (x, y))
        return img

    def _ensure_thumb_for_roll(self, roll):
        """Ensure a thumbnail PhotoImage exists for a roll; return it or None."""
        rid = roll.get("id")
        if not rid:
            return None
        if rid in self.thumb_cache:
            return self.thumb_cache[rid]
        b64 = roll.get("photo_b64")
        if not b64:
            return None
        try:
            data = base64.b64decode(b64)
            tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
            tmpf.write(data)
            tmpf.flush()
            tmpf.close()
            img = tk.PhotoImage(file=tmpf.name)
            w = img.width()
            h = img.height()
            subs = max(1, int(max(w, h) / THUMBNAIL_SIZE))
            if subs > 1:
                try:
                    img = img.subsample(subs, subs)
                except Exception:
                    pass
            self.thumb_cache[rid] = img
            return img
        except Exception:
            return None

    def _create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        frame_rolls = ttk.Frame(notebook)
        notebook.add(frame_rolls, text="Filament Rolls")

        power_frame = ttk.Frame(frame_rolls)
        power_frame.pack(fill="x", padx=6, pady=6)

        ttk.Label(power_frame, text="Filter by:").pack(side="left")
        self.filter_field = ttk.Combobox(power_frame, values=["Color", "Material", "Description"], state="readonly", width=12)
        self.filter_field.current(0)
        self.filter_field.pack(side="left", padx=(4, 4))
        self.filter_var = tk.StringVar()
        e = ttk.Entry(power_frame, textvariable=self.filter_var)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<KeyRelease>", lambda ev: self.apply_filter())
        ttk.Button(power_frame, text="Clear", command=self.clear_filter).pack(side="left", padx=4)

        columns = ("thumb", "color", "material", "remaining_grams", "description", "price_per_gram")
        tree_frame = ttk.Frame(frame_rolls)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("thumb", text="", command=lambda: self.sort_by("thumb"))
        self.tree.heading("color", text="Color", command=lambda: self.sort_by("color"))
        self.tree.heading("material", text="Material", command=lambda: self.sort_by("material"))
        self.tree.heading("remaining_grams", text="Remaining (g)", command=lambda: self.sort_by("remaining_grams"))
        self.tree.heading("description", text="Description", command=lambda: self.sort_by("description"))
        self.tree.heading("price_per_gram", text="Price / g", command=lambda: self.sort_by("price_per_gram"))
        self.tree.column("thumb", width=THUMBNAIL_SIZE+8, anchor="center")
        self.tree.column("color", width=100, anchor="w")
        self.tree.column("material", width=100, anchor="w")
        self.tree.column("remaining_grams", width=120, anchor="e")
        self.tree.column("description", width=250, anchor="w")
        self.tree.column("price_per_gram", width=90, anchor="e")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(frame_rolls)
        btn_frame.pack(fill="x", padx=6, pady=(0,6))
        ttk.Button(btn_frame, text="Add Roll", command=self.cmd_add_roll).pack(side="left")
        ttk.Button(btn_frame, text="Edit Roll", command=self.cmd_edit_roll).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remove Roll", command=self.cmd_remove_roll).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Use Filament", command=self.cmd_use_filament).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Settings", command=self.cmd_settings).pack(side="right")
        ttk.Button(btn_frame, text="Refresh", command=self.populate_table).pack(side="right", padx=4)

        frame_stats = ttk.Frame(notebook)
        notebook.add(frame_stats, text="Stats")

        stats_top = ttk.Frame(frame_stats)
        stats_top.pack(fill="x", padx=6, pady=6)
        self.stats_label = ttk.Label(stats_top, text="", justify="left")
        self.stats_label.pack(side="left", anchor="n")

        proj_frame = ttk.LabelFrame(frame_stats, text="Projects")
        proj_frame.pack(fill="both", expand=False, padx=6, pady=6)
        self.projects_tree = ttk.Treeview(proj_frame, columns=("grams", "cost", "events"), show="headings", height=6)
        self.projects_tree.heading("grams", text="Grams used")
        self.projects_tree.heading("cost", text="Estimated $")
        self.projects_tree.heading("events", text="# events")
        self.projects_tree.column("grams", width=100, anchor="e")
        self.projects_tree.column("cost", width=100, anchor="e")
        self.projects_tree.column("events", width=80, anchor="e")
        self.projects_tree.pack(side="left", fill="both", expand=True)
        ttk.Button(proj_frame, text="Export CSV", command=self.export_projects_csv).pack(side="right", padx=6, pady=6)

        charts_frame = ttk.Frame(frame_stats)
        charts_frame.pack(fill="both", expand=True, padx=6, pady=6)
        if HAS_MATPLOTLIB:
            chart_notebook = ttk.Notebook(charts_frame)
            chart_notebook.pack(fill="both", expand=True)
            self.chart_material = ttk.Frame(chart_notebook)
            self.chart_timeline = ttk.Frame(chart_notebook)
            chart_notebook.add(self.chart_material, text="By Material")
            chart_notebook.add(self.chart_timeline, text="Timeline")
            ttk.Button(self.chart_material, text="Refresh Charts", command=self.refresh_charts).pack()
        else:
            label = ttk.Label(charts_frame, text="Charts unavailable. Install matplotlib with:\n\npip install matplotlib")
            label.pack(pady=20)

        self.tree.bind("<Double-1>", self.on_tree_double)

    def clear_filter(self):
        self.filter_var.set("")
        self.apply_filter()

    def apply_filter(self):
        """Filter visible rows according to quick filter."""
        q = self.filter_var.get().strip().lower()
        field = self.filter_field.get().lower()
        for it in self.tree.get_children():
            self.tree.delete(it)
        for roll in self.data.get("active", []):
            if q:
                target = ""
                if field == "color":
                    target = roll.get("color", "")
                elif field == "material":
                    target = roll.get("material", "")
                elif field == "description":
                    target = roll.get("description", "")
                if q not in str(target).lower():
                    continue
            self._insert_roll_row(roll)

    def populate_table(self):
        """Populate the Treeview from active rolls, preserving sort state."""
        for it in self.tree.get_children():
            self.tree.delete(it)
        for roll in self.data.get("active", []):
            self._insert_roll_row(roll)
        col, asc = self.last_sort
        self.sort_by(col, toggle=False, ascending=asc)

    def _insert_roll_row(self, roll):
        """Insert a single roll row into the treeview."""
        rid = roll.get("id")
        thumb = self._ensure_thumb_for_roll(roll)
        img = None
        if thumb:
            img = thumb
            self.row_images[rid] = img
        rem = safe_float_from_str(roll.get("remaining_grams", 0.0), 0.0)
        threshold = self._threshold_for_material(roll.get("material", ""))
        is_below = rem < threshold
        status_icon = self.icon_green
        if rem < DEFAULT_THRESHOLDS["default"]["red"] or rem < threshold:
            status_icon = self.icon_red
        elif rem < DEFAULT_THRESHOLDS["default"]["yellow"]:
            status_icon = self.icon_yellow
        col_color = roll.get("color", "")
        col_material = roll.get("material", "")
        col_remaining = f"{rem:.1f}"
        col_desc = roll.get("description", "")
        col_price = f"{roll.get('price_per_gram', 0.0):.4f}"
        values = ("" , col_color, col_material, col_remaining, col_desc, col_price)
        iid = self.tree.insert("", "end", values=values, tags=(rid,))
        if img:
            try:
                self.tree.set(iid, column="thumb", value=" ")
                self.tree.item(iid, image=img)
            except Exception:
                pass
        if is_below:
            self.tree.item(iid, tags=("low", rid))
            self.tree.tag_configure("low", background="#ffe6e6")
            self.bell()
        self.tree.set(iid, "color", col_color)  
        return iid

    def _get_roll_by_tree_iid(self, iid):
        tags = self.tree.item(iid, "tags")
        if not tags:
            return None
        rid = tags[-1]
        for r in self.data.get("active", []):
            if r.get("id") == rid:
                return r
        for r in self.data.get("archived", []):
            if r.get("id") == rid:
                return r
        return None

    def cmd_add_roll(self):
        dialog = RollDialog(self, title="Add Roll")
        self.wait_window(dialog.top)
        if not dialog.result:
            return
        roll = dialog.result
        roll["price_per_gram"] = compute_price_per_gram(roll.get("initial_price", 0.0), roll.get("initial_weight", 0.0))
        roll = ensure_fields(roll)
        self.data.setdefault("active", []).append(roll)
        self.save_data()
        self.populate_table()
        self.update_stats_tab()

    def cmd_edit_roll(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Edit Roll", "Select a roll to edit.")
            return
        iid = sel[0]
        roll = self._get_roll_by_tree_iid(iid)
        if not roll:
            messagebox.showerror("Edit Roll", "Failed to find selected roll.")
            return
        copy_roll = dict(roll)
        dialog = RollDialog(self, title="Edit Roll", roll=copy_roll)
        self.wait_window(dialog.top)
        if not dialog.result:
            return
        new_roll = dialog.result
        for k in ["color", "material", "remaining_grams", "description", "initial_weight", "initial_price", "photo_b64"]:
            if k in new_roll:
                roll[k] = new_roll[k]
        roll["price_per_gram"] = compute_price_per_gram(roll.get("initial_price", 0.0), roll.get("initial_weight", 0.0))
        self.save_data()
        self.populate_table()
        self.update_stats_tab()

    def cmd_remove_roll(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Remove Roll", "Select one or more rolls to archive.")
            return
        if not messagebox.askyesno("Archive Rolls", f"Archive {len(sel)} selected roll(s)?"):
            return
        moved = 0
        for iid in sel:
            roll = self._get_roll_by_tree_iid(iid)
            if not roll:
                continue
            try:
                self.data["active"] = [r for r in self.data["active"] if r.get("id") != roll.get("id")]
                self.data.setdefault("archived", []).append(roll)
                moved += 1
            except Exception:
                pass
        if moved:
            self.save_data()
            self.populate_table()
            self.update_stats_tab()

    def cmd_use_filament(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Use Filament", "Select a roll to use.")
            return
        iid = sel[0]
        roll = self._get_roll_by_tree_iid(iid)
        if not roll:
            messagebox.showerror("Use Filament", "Failed to identify selected roll.")
            return
        dialog = UseFilamentDialog(self, roll, projects=self.data.get("projects", {}))
        self.wait_window(dialog.top)
        if not dialog.result:
            return
        used_grams = dialog.result.get("used_grams", 0.0)
        project_name = dialog.result.get("project")
        used_grams = safe_float_from_str(used_grams, 0.0)
        roll["remaining_grams"] = max(0.0, safe_float_from_str(roll.get("remaining_grams", 0.0)) - used_grams)
        roll["used_grams"] = safe_float_from_str(roll.get("used_grams", 0.0)) + used_grams
        cost = used_grams * safe_float_from_str(roll.get("price_per_gram", 0.0))
        ev = {"roll_id": roll.get("id"), "project": project_name, "used_grams": used_grams, "cost": cost, "ts": now_iso()}
        self.data.setdefault("usage_events", []).append(ev)
        if project_name:
            p = self.data.setdefault("projects", {}).setdefault(project_name, {"grams": 0.0, "cost": 0.0, "events": 0})
            p["grams"] = safe_float_from_str(p.get("grams", 0.0)) + used_grams
            p["cost"] = safe_float_from_str(p.get("cost", 0.0)) + cost
            p["events"] = int(p.get("events", 0)) + 1
        if roll["remaining_grams"] <= 0:
            self.data["active"] = [r for r in self.data.get("active", []) if r.get("id") != roll.get("id")]
            self.data.setdefault("archived", []).append(roll)
        self.save_data()
        self.populate_table()
        self.update_stats_tab()
        self.check_low_stock_nonblocking()

    def cmd_settings(self):
        dialog = SettingsDialog(self, thresholds=self.data.get("thresholds", {}))
        self.wait_window(dialog.top)
        if dialog.result is None:
            return
        self.data["thresholds"] = dialog.result
        self.save_data()
        self.check_low_stock_nonblocking()

    def _threshold_for_material(self, material: str) -> float:
        thr = self.data.get("thresholds", {})
        material_key = (material or "").strip()
        if material_key and material_key in thr:
            try:
                return safe_float_from_str(thr[material_key], DEFAULT_THRESHOLDS["default"]["red"])
            except Exception:
                return DEFAULT_THRESHOLDS["default"]["red"]
        return DEFAULT_THRESHOLDS["default"]["red"]

    def check_low_stock_nonblocking(self):
        """Non-blocking alert listing rolls below per-material threshold."""
        low_rolls = []
        for r in self.data.get("active", []):
            rem = safe_float_from_str(r.get("remaining_grams", 0.0), 0.0)
            thr = self._threshold_for_material(r.get("material", ""))
            if rem < thr:
                low_rolls.append((r, rem, thr))
        if not low_rolls:
            return
        top = tk.Toplevel(self)
        top.title("Low-stock alerts")
        top.geometry("400x200")
        msg = tk.Text(top, height=10, width=60)
        msg.pack(fill="both", expand=True)
        for r, rem, thr in low_rolls:
            msg.insert("end", f"{r.get('color','')} {r.get('material','')} — {rem:.1f} g (threshold {thr} g)\n")
        msg.config(state="disabled")
        ttk.Button(top, text="Dismiss", command=top.destroy).pack(pady=6)
        self.bell()
        for iid in self.tree.get_children():
            roll = self._get_roll_by_tree_iid(iid)
            if roll and any(r.get("id") == roll.get("id") for r,_,_ in low_rolls):
                self.tree.item(iid, tags=("low", roll.get("id")))
                self.tree.tag_configure("low", background="#ffe6e6")

    def update_stats_tab(self):
        rolls_used = len(self.data.get("archived", []))
        rolls_left = len(self.data.get("active", []))
        total_rolls = rolls_used + rolls_left
        total_filament_used = 0.0
        total_money_used = 0.0
        for r in self.data.get("archived", []) + self.data.get("active", []):
            total_filament_used += safe_float_from_str(r.get("used_grams", 0.0))
            total_money_used += safe_float_from_str(r.get("used_grams", 0.0)) * safe_float_from_str(r.get("price_per_gram", 0.0))
        txt = (
            f"Rolls used (archived): {rolls_used}\n"
            f"Rolls left (active): {rolls_left}\n"
            f"Total filament used: {total_filament_used:.1f} g\n"
            f"Total rolls tracked: {total_rolls}\n"
            f"Total money used: {format_money(total_money_used)}"
        )
        self.stats_label.config(text=txt)
        for it in self.projects_tree.get_children():
            self.projects_tree.delete(it)
        for pname, pdata in sorted(self.data.get("projects", {}).items()):
            grams = safe_float_from_str(pdata.get("grams", 0.0))
            cost = safe_float_from_str(pdata.get("cost", 0.0))
            events = int(pdata.get("events", 0))
            self.projects_tree.insert("", "end", values=(f"{grams:.1f}", format_money(cost), str(events)), text=pname, tags=(pname,))
        if HAS_MATPLOTLIB:
            self.refresh_charts()

    def export_projects_csv(self):
        try:
            with open(PROJECT_CSV, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["project", "grams", "cost", "events"])
                for pname, pdata in sorted(self.data.get("projects", {}).items()):
                    w.writerow([pname, f"{safe_float_from_str(pdata.get('grams',0.0)):.2f}", f"{safe_float_from_str(pdata.get('cost',0.0)):.2f}", int(pdata.get("events", 0))])
            messagebox.showinfo("Export CSV", f"Exported project usage to {PROJECT_CSV}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to write CSV: {e}")

    def refresh_charts(self):
        if not HAS_MATPLOTLIB:
            return
        mat_totals = {}
        date_totals = {}
        for ev in self.data.get("usage_events", []):
            rid = ev.get("roll_id")
            material = "Unknown"
            for r in self.data.get("active", []) + self.data.get("archived", []):
                if r.get("id") == rid:
                    material = r.get("material", "Unknown")
                    break
            grams = safe_float_from_str(ev.get("used_grams", 0.0))
            mat_totals[material] = mat_totals.get(material, 0.0) + grams
            ts = ev.get("ts")
            try:
                d = datetime.fromisoformat(ts).date().isoformat()
            except Exception:
                d = date.today().isoformat()
            date_totals[d] = date_totals.get(d, 0.0) + grams
        for child in self.chart_material.winfo_children():
            child.destroy()
        for child in self.chart_timeline.winfo_children():
            child.destroy()
        fig1 = Figure(figsize=(5,3))
        ax1 = fig1.add_subplot(111)
        mats = list(mat_totals.keys()) or ["None"]
        grams = [mat_totals.get(m,0.0) for m in mats]
        ax1.bar(mats, grams)
        ax1.set_title("Grams used by Material")
        ax1.set_ylabel("Grams")
        canvas1 = FigureCanvasTkAgg(fig1, master=self.chart_material)
        canvas1.draw()
        canvas1.get_tk_widget().pack(fill="both", expand=True)
        fig2 = Figure(figsize=(5,3))
        ax2 = fig2.add_subplot(111)
        days = sorted(date_totals.keys())
        vals = [date_totals.get(d,0.0) for d in days]
        ax2.plot(days, vals, marker="o")
        ax2.set_title("Grams used over time")
        ax2.set_ylabel("Grams")
        ax2.tick_params(axis='x', rotation=45)
        canvas2 = FigureCanvasTkAgg(fig2, master=self.chart_timeline)
        canvas2.draw()
        canvas2.get_tk_widget().pack(fill="both", expand=True)

    def on_tree_double(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        roll = self._get_roll_by_tree_iid(iid)
        if not roll:
            return
        if roll.get("photo_b64"):
            self.open_lightbox(roll)
        else:
            self.cmd_edit_roll()

    def open_lightbox(self, roll):
        b64 = roll.get("photo_b64")
        if not b64:
            messagebox.showinfo("Photo", "No photo attached.")
            return
        try:
            data = base64.b64decode(b64)
            tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
            tmpf.write(data)
            tmpf.flush()
            tmpf.close()
            top = tk.Toplevel(self)
            top.title(f"Photo: {roll.get('color')} {roll.get('material')}")
            img = tk.PhotoImage(file=tmpf.name)
            top.img = img
            lbl = ttk.Label(top, image=img)
            lbl.pack()
            ttk.Button(top, text="Close", command=top.destroy).pack(pady=6)
        except Exception as e:
            messagebox.showerror("Photo error", f"Failed to open photo:\n{e}")


class RollDialog:
    """Dialog for adding/editing a roll."""
    def __init__(self, parent: FilamentManagerApp, title="Roll", roll=None):
        self.parent = parent
        self.result = None
        self.roll = roll or {}
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.transient(parent)
        self.top.grab_set()
        frm = ttk.Frame(self.top)
        frm.pack(padx=8, pady=8, fill="both", expand=True)
        ttk.Label(frm, text="Color:").grid(row=0, column=0, sticky="e")
        self.color_var = tk.StringVar(value=self.roll.get("color", ""))
        ttk.Entry(frm, textvariable=self.color_var).grid(row=0, column=1, sticky="we")
        ttk.Label(frm, text="Material:").grid(row=1, column=0, sticky="e")
        self.material_var = tk.StringVar(value=self.roll.get("material", ""))
        ttk.Entry(frm, textvariable=self.material_var).grid(row=1, column=1, sticky="we")
        ttk.Label(frm, text="Initial weight (g):").grid(row=2, column=0, sticky="e")
        self.initial_weight_var = tk.StringVar(value=str(self.roll.get("initial_weight", "")))
        ttk.Entry(frm, textvariable=self.initial_weight_var).grid(row=2, column=1, sticky="we")
        ttk.Label(frm, text="Initial price ($):").grid(row=3, column=0, sticky="e")
        self.initial_price_var = tk.StringVar(value=str(self.roll.get("initial_price", "")))
        ttk.Entry(frm, textvariable=self.initial_price_var).grid(row=3, column=1, sticky="we")
        ttk.Label(frm, text="Remaining (g):").grid(row=4, column=0, sticky="e")
        self.remaining_var = tk.StringVar(value=str(self.roll.get("remaining_grams", "")))
        ttk.Entry(frm, textvariable=self.remaining_var).grid(row=4, column=1, sticky="we")
        ttk.Label(frm, text="Description:").grid(row=5, column=0, sticky="ne")
        self.desc_text = tk.Text(frm, height=4, width=30)
        self.desc_text.grid(row=5, column=1, sticky="we")
        self.desc_text.insert("1.0", self.roll.get("description", ""))
        photo_frame = ttk.Frame(frm)
        photo_frame.grid(row=6, column=0, columnspan=2, pady=(6,0))
        ttk.Button(photo_frame, text="Add/Change Photo", command=self.add_change_photo).pack(side="left")
        ttk.Button(photo_frame, text="Remove Photo", command=self.remove_photo).pack(side="left", padx=(6,0))
        self.photo_b64 = self.roll.get("photo_b64", None)

        btns = ttk.Frame(self.top)
        btns.pack(pady=8)
        ttk.Button(btns, text="Cancel", command=self._on_cancel).pack(side="right", padx=6)
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")
        frm.columnconfigure(1, weight=1)

    def add_change_photo(self):
        f = filedialog.askopenfilename(title="Select image", filetypes=[("Image files", "*.png *.gif *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not f:
            return
        try:
            with open(f, "rb") as fh:
                b = fh.read()
            self.photo_b64 = base64.b64encode(b).decode("ascii")
            messagebox.showinfo("Photo", "Photo added (saved after OK).")
        except Exception as e:
            messagebox.showerror("Photo", f"Failed to read image: {e}")

    def remove_photo(self):
        self.photo_b64 = None
        messagebox.showinfo("Photo", "Photo removed (saved after OK).")

    def _on_cancel(self):
        self.result = None
        self.top.destroy()

    def _on_ok(self):
        iw = safe_float_from_str(self.initial_weight_var.get(), None)
        ip = safe_float_from_str(self.initial_price_var.get(), None)
        rem = safe_float_from_str(self.remaining_var.get(), None)
        if iw is None or iw < 0:
            messagebox.showerror("Validation", "Invalid initial weight.")
            return
        if ip is None or ip < 0:
            messagebox.showerror("Validation", "Invalid initial price.")
            return
        if rem is None or rem < 0:
            messagebox.showerror("Validation", "Invalid remaining grams.")
            return

        newroll = {
            "color": self.color_var.get().strip(),
            "material": self.material_var.get().strip(),
            "initial_weight": iw,
            "initial_price": ip,
            "remaining_grams": rem,
            "description": self.desc_text.get("1.0", "end").strip(),
            "photo_b64": self.photo_b64,
        }

        if self.roll and self.roll.get("id"):
            newroll["id"] = self.roll.get("id")
            newroll["created_at"] = self.roll.get("created_at", now_iso())
            newroll["used_grams"] = self.roll.get("used_grams", 0.0)
        self.result = newroll
        self.top.destroy()

class UseFilamentDialog:
    """Dialog to use filament from a roll and attribute to a project."""
    def __init__(self, parent: FilamentManagerApp, roll: dict, projects: dict):
        self.parent = parent
        self.roll = roll
        self.projects = projects or {}
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("Use Filament")
        self.top.transient(parent)
        self.top.grab_set()
        f = ttk.Frame(self.top)
        f.pack(padx=8, pady=8)
        ttk.Label(f, text=f"Roll: {roll.get('color','')} {roll.get('material','')}").grid(row=0, column=0, columnspan=2)
        ttk.Label(f, text=f"Remaining: {roll.get('remaining_grams',0.0)} g").grid(row=1, column=0, columnspan=2)
        ttk.Label(f, text="Use grams:").grid(row=2, column=0, sticky="e")
        self.grams_var = tk.StringVar(value="0")
        ttk.Entry(f, textvariable=self.grams_var).grid(row=2, column=1, sticky="we")
        ttk.Label(f, text="Project:").grid(row=3, column=0, sticky="e")
        self.project_var = tk.StringVar()
        cb = ttk.Combobox(f, values=list(self.projects.keys()), textvariable=self.project_var)
        cb.grid(row=3, column=1, sticky="we")
        ttk.Button(f, text="New Project...", command=self.new_project).grid(row=4, column=1, sticky="e")
        btns = ttk.Frame(self.top)
        btns.pack(pady=6)
        ttk.Button(btns, text="Cancel", command=self._on_cancel).pack(side="right", padx=6)
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")
        f.columnconfigure(1, weight=1)

    def new_project(self):
        name = simpledialog.askstring("New project", "Project name:", parent=self.top)
        if not name:
            return
        self.project_var.set(name)
        self.projects.setdefault(name, {"grams": 0.0, "cost": 0.0, "events": 0})

    def _on_cancel(self):
        self.result = None
        self.top.destroy()

    def _on_ok(self):
        g = safe_float_from_str(self.grams_var.get(), None)
        if g is None or g <= 0:
            messagebox.showerror("Validation", "Enter a positive number of grams.")
            return

        self.result = {"used_grams": g, "project": self.project_var.get().strip()}
        self.top.destroy()

class SettingsDialog:
    """Settings for per-material thresholds."""
    def __init__(self, parent: FilamentManagerApp, thresholds: dict):
        self.parent = parent
        self.original = thresholds or {}
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("Settings - Low-stock thresholds")
        self.top.transient(parent)
        self.top.grab_set()
        frame = ttk.Frame(self.top)
        frame.pack(padx=8, pady=8, fill="both", expand=True)
        ttk.Label(frame, text="Per-material low-stock thresholds (grams). Leave blank to use default 300g").pack()
        self.entries = {}
        row = 1

        materials = set(r.get("material","") for r in parent.data.get("active", []) + parent.data.get("archived", []))

        for k in self.original.keys():
            materials.add(k)
        materials = sorted([m for m in materials if m])
        for m in materials:
            ttk.Label(frame, text=m).grid(row=row, column=0, sticky="e")
            var = tk.StringVar(value=str(self.original.get(m, "")))
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky="we")
            self.entries[m] = var
            row += 1

        ttk.Label(frame, text="Add material:").grid(row=row, column=0, sticky="e")
        self.new_mat_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.new_mat_var).grid(row=row, column=1, sticky="we")
        ttk.Button(frame, text="Add", command=self._add_material_row).grid(row=row, column=2, padx=6)
        row += 1

        btns = ttk.Frame(self.top)
        btns.pack(pady=8)
        ttk.Button(btns, text="Cancel", command=self._on_cancel).pack(side="right", padx=6)
        ttk.Button(btns, text="Save", command=self._on_save).pack(side="right")

        frame.columnconfigure(1, weight=1)

    def _add_material_row(self):
        name = self.new_mat_var.get().strip()
        if not name:
            return
        if name in self.entries:
            messagebox.showinfo("Exists", "Material already present.")
            return
        var = tk.StringVar(value="")
        r = max(self.entries.keys(), default=None)

        self.entries[name] = var
 
        self.top.destroy()
        self.__init__(self.parent, thresholds=self.original)

    def _on_cancel(self):
        self.result = None
        self.top.destroy()

    def _on_save(self):
        newthr = {}
        for m, var in self.entries.items():
            v = var.get().strip()
            if not v:
                continue
            f = safe_float_from_str(v, None)
            if f is None or f <= 0:
                messagebox.showerror("Validation", f"Invalid threshold for {m}.")
                return
            newthr[m] = f
        self.result = newthr
        self.top.destroy()


def main():
    try:
        app = FilamentManagerApp()
        app.mainloop()
    except Exception as e:
        print("Fatal error:", e)
        traceback.print_exc()

if __name__ == "__main__":
    main()
