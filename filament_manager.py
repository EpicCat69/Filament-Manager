import json
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import base64
from io import BytesIO

DATA_FILE = "filament_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"active": [], "archived": []}
    with open(DATA_FILE, "r") as file:
        return json.load(file)

def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

def create_colored_image(color, size=16):
    img = tk.PhotoImage(width=size, height=size)
    for x in range(size):
        for y in range(size):
            img.put(color, (x, y))
    return img

class FilamentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Filament Roll Manager")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        width = int(screen_width * 0.75)
        height = int(screen_height * 0.75)
        root.geometry(f"{width}x{height}")

        self.data = load_data()
        self.active_rolls = self.data.get("active", [])
        self.archived_rolls = self.data.get("archived", [])

        self.green_img = create_colored_image("green")
        self.yellow_img = create_colored_image("yellow")
        self.red_img = create_colored_image("red")

        self.create_widgets()
        self.refresh_list()
        self.update_stats()

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.frame_list = ttk.Frame(self.notebook)
        self.notebook.add(self.frame_list, text="Filament Rolls")

        self.frame_stats = ttk.Frame(self.notebook)
        self.notebook.add(self.frame_stats, text="Stats")

        self.tree = ttk.Treeview(self.frame_list, columns=("Color", "Material", "Remaining", "Description", "Price/g"), show="headings", height=15)
        self.tree["columns"] = ("Color", "Material", "Remaining", "Description", "Price/g")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=30, anchor=tk.CENTER)
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        btn_frame = tk.Frame(self.frame_list)
        btn_frame.pack(fill=tk.X, pady=5)

        tk.Button(btn_frame, text="Add Roll", command=self.add_roll).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Edit Roll", command=self.edit_roll).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Remove Roll", command=self.remove_roll).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Use Filament", command=self.use_filament).pack(side=tk.LEFT, padx=5)

        self.stats_vars = {
            "rolls_used": tk.StringVar(),
            "rolls_left": tk.StringVar(),
            "total_filament_used": tk.StringVar(),
            "total_rolls_tracked": tk.StringVar(),
            "total_money_used": tk.StringVar(),
        }
        for var in self.stats_vars.values():
            label = ttk.Label(self.frame_stats, textvariable=var, font=("Arial", 14))
            label.pack(anchor=tk.W, padx=10, pady=5)

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        new_active = []
        for idx, roll in enumerate(self.active_rolls):
            if roll["remaining_grams"] <= 0:
                self.archived_rolls.append(roll)
                continue
            image = self.get_color_image(roll["remaining_grams"])
            price_per_g = roll.get("price_per_gram", 0.0)
            self.tree.insert("", tk.END, iid=idx, image=image, values=(
                roll["color"],
                roll["material"],
                f'{roll["remaining_grams"]:.1f}',
                roll.get("description", ""),
                f"${price_per_g:.4f}"
            ))
            new_active.append(roll)

        self.active_rolls = new_active
        self.data["active"] = self.active_rolls
        self.data["archived"] = self.archived_rolls
        save_data(self.data)
        self.update_stats()

    def get_color_image(self, grams):
        if grams >= 1000:
            return self.green_img
        elif 300 <= grams < 1000:
            return self.yellow_img
        elif 1 <= grams < 300:
            return self.red_img
        else:
            return None

    def add_roll(self):
        color = self.ask_until_valid("Color", "Enter the color of the roll:")
        if color is None:
            return
        material = self.ask_until_valid("Material", "Enter the material (e.g., PLA, ABS):")
        if material is None:
            return

        remaining = self.ask_float_until_valid("Weight", "Enter remaining grams:", positive=True)
        if remaining is None:
            return

        description = simpledialog.askstring("Description", "Enter a short description (optional):", parent=self.root) or ""

        price = self.ask_float_until_valid("Price", "Enter the price of the roll ($):", positive=True)
        if price is None:
            return

        price_per_gram = price / remaining if remaining > 0 else 0.0

        roll = {
            "color": color,
            "material": material,
            "remaining_grams": remaining,
            "description": description,
            "price_per_gram": price_per_gram,
            "initial_weight": remaining,
            "initial_price": price,
            "used_grams": 0.0,
        }

        self.active_rolls.append(roll)
        self.data["active"] = self.active_rolls
        save_data(self.data)
        self.refresh_list()

    def ask_until_valid(self, title, prompt):
        while True:
            res = simpledialog.askstring(title, prompt, parent=self.root)
            if res is None:
                return None
            if res.strip():
                return res.strip()
            messagebox.showerror("Error", f"{title} cannot be empty.", parent=self.root)

    def ask_float_until_valid(self, title, prompt, positive=False):
        while True:
            res = simpledialog.askstring(title, prompt, parent=self.root)
            if res is None:
                return None
            try:
                val = float(res.replace(',', '.'))
                if positive and val <= 0:
                    messagebox.showerror("Error", f"{title} must be positive.", parent=self.root)
                    continue
                return val
            except ValueError:
                messagebox.showerror("Error", f"Invalid number for {title}.", parent=self.root)

    def remove_roll(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No roll selected.", parent=self.root)
            return
        idx = int(selected[0])

        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to remove the selected roll? Stats will be saved.", parent=self.root)
        if not confirm:
            return

        roll = self.active_rolls.pop(idx)
        self.archived_rolls.append(roll)
        self.data["active"] = self.active_rolls
        self.data["archived"] = self.archived_rolls
        save_data(self.data)
        self.refresh_list()

    def use_filament(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No roll selected.", parent=self.root)
            return
        idx = int(selected[0])

        confirm = messagebox.askyesno("Confirm Use", "Confirm use filament from the selected roll?", parent=self.root)
        if not confirm:
            return

        used = self.ask_float_until_valid("Usage", "Enter amount used in grams:", positive=True)
        if used is None:
            return

        if used > self.active_rolls[idx]["remaining_grams"]:
            messagebox.showwarning("Warning", "Used amount exceeds remaining grams. Setting remaining to 0.", parent=self.root)
            used = self.active_rolls[idx]["remaining_grams"]

        self.active_rolls[idx]["remaining_grams"] -= used
        self.active_rolls[idx]["used_grams"] = self.active_rolls[idx].get("used_grams", 0) + used

        if self.active_rolls[idx]["remaining_grams"] <= 0:
            roll = self.active_rolls.pop(idx)
            self.archived_rolls.append(roll)

        self.data["active"] = self.active_rolls
        self.data["archived"] = self.archived_rolls
        save_data(self.data)
        self.refresh_list()

    def edit_roll(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No roll selected.", parent=self.root)
            return
        idx = int(selected[0])
        roll = self.active_rolls[idx]

        new_color = self.ask_until_valid("Edit Color", f"Color ({roll['color']}):")
        if new_color is None:
            return
        new_material = self.ask_until_valid("Edit Material", f"Material ({roll['material']}):")
        if new_material is None:
            return
        new_remaining = self.ask_float_until_valid("Edit Remaining grams", f"Remaining grams ({roll['remaining_grams']}):", positive=True)
        if new_remaining is None:
            return
        new_description = simpledialog.askstring("Edit Description", f"Description ({roll.get('description', '')}):", parent=self.root)
        if new_description is None:
            return
        new_price_per_gram = self.ask_float_until_valid("Edit Price per gram", f"Price per gram (${roll.get('price_per_gram', 0.0):.4f}):", positive=True)
        if new_price_per_gram is None:
            return

        roll["color"] = new_color
        roll["material"] = new_material
        roll["remaining_grams"] = new_remaining
        roll["description"] = new_description
        roll["price_per_gram"] = new_price_per_gram

        self.data["active"][idx] = roll
        save_data(self.data)
        self.refresh_list()

    def update_stats(self):
        all_rolls = self.active_rolls + self.archived_rolls

        total_rolls_tracked = len(all_rolls)
        rolls_left = len(self.active_rolls)
        rolls_used = len(self.archived_rolls)

        total_filament_used = 0.0
        total_money_used = 0.0

        for roll in all_rolls:
            used = roll.get("used_grams", 0)
            total_filament_used += used
            price_per_gram = roll.get("price_per_gram", 0)
            total_money_used += used * price_per_gram

        self.stats_vars["rolls_used"].set(f"Rolls used (archived): {rolls_used}")
        self.stats_vars["rolls_left"].set(f"Rolls left (active): {rolls_left}")
        self.stats_vars["total_filament_used"].set(f"Total filament used (grams): {total_filament_used:.2f}")
        self.stats_vars["total_rolls_tracked"].set(f"Total rolls tracked: {total_rolls_tracked}")
        self.stats_vars["total_money_used"].set(f"Total money used ($): {total_money_used:.2f}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FilamentApp(root)
    root.mainloop()
