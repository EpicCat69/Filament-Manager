import json
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

DATA_FILE = "filament_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as file:
        return json.load(file)

def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

class FilamentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Filament Roll Manager")
        self.data = load_data()
        self.create_widgets()
        self.refresh_list()

    def create_widgets(self):
        self.tree = ttk.Treeview(self.root, columns=("Color", "Material", "Remaining", "Description"), show="headings")
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
        self.tree.pack(fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="Add Roll", command=self.add_roll).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(btn_frame, text="Remove Roll", command=self.remove_roll).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(btn_frame, text="Use Filament", command=self.use_filament).pack(side=tk.LEFT, padx=5, pady=5)

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for roll in self.data:
            self.tree.insert("", tk.END, values=(roll["color"], roll["material"], roll["remaining_grams"], roll["description"]))

    def add_roll(self):
        color = simpledialog.askstring("Color", "Enter the color of the roll:")
        material = simpledialog.askstring("Material", "Enter the material (e.g., PLA, ABS):")
        try:
            remaining = float(simpledialog.askstring("Weight", "Enter remaining grams:"))
        except (TypeError, ValueError):
            messagebox.showerror("Error", "Invalid number for grams.")
            return
        description = simpledialog.askstring("Description", "Enter a short description:")

        self.data.append({
            "color": color,
            "material": material,
            "remaining_grams": remaining,
            "description": description
        })
        save_data(self.data)
        self.refresh_list()

    def remove_roll(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No roll selected.")
            return
        index = self.tree.index(selected[0])
        del self.data[index]
        save_data(self.data)
        self.refresh_list()

    def use_filament(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No roll selected.")
            return
        index = self.tree.index(selected[0])
        try:
            used = float(simpledialog.askstring("Usage", "Enter amount used in grams:"))
        except (TypeError, ValueError):
            messagebox.showerror("Error", "Invalid number.")
            return
        self.data[index]["remaining_grams"] -= used
        if self.data[index]["remaining_grams"] < 0:
            self.data[index]["remaining_grams"] = 0
        save_data(self.data)
        self.refresh_list()

if __name__ == "__main__":
    root = tk.Tk()
    app = FilamentApp(root)
    root.mainloop()
