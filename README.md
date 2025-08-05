# Filament-Manager
A simple desktop app to manage 3D printer filament rolls. Track color, material, remaining grams, and usage after prints. Add, edit, or remove rolls with a user-friendly GUI. Built with Python and Tkinter.


---

## ✨ Features

- 📋 View all filament rolls in a clean table
- ➕ Add new rolls with color, material, grams left, description, and price
- 🗑️ Remove rolls when empty or unused
- 🎯 Log filament usage (grams) after each print
- 💾 Data is saved locally in `filament_data.json`
- 📃 Saves Stats like gram used, money spent, and rolls used
- 🪟 Built with Python & Tkinter — no internet needed

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+ (Windows, Mac, or Linux)
- Tkinter (comes with standard Python install)

### 2. Run the App
```bash
python filament_manager.py
```

### 3. Optional: Create Executable (Windows)
```bash
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed filament_manager.py
```
Your `.exe` will be in the `dist/` folder.

---

## 📂 Data Format

The app stores your filament rolls in `filament_data.json` like this:

```json
[
  {
    "color": "Red",
    "material": "PLA",
    "remaining_grams": 850,
    "description": "Silk glossy finish"
  }
]
```

---

## 🔗 Links

- [View Project on GitHub](https://github.com/EpicCat69/Filament-Manager)

---

## 📃 License

MIT License — free to use and modify.

---

Made with 💻 and 3D printing love by **SOEP**
