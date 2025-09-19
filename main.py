#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini-Selector GUI (Tkinter)
---------------------------
Funktion:
- Liest CSV-Dateien aus dem Ordner ./db (jeder Typ = 1 Datei).
- Drop-down zur Auswahl des Typs (Dateiname ohne Endung).
- Eingabe der Länge + Einheiten (m / cm).
- Berechnet required_cetta = Länge_in_m * cetta_pro_meter (aus CSV-Zeile).
- Sucht die **kleinste Außen-Dimension**, deren cetta_max >= required_cetta ist.
  - Sortierkriterium: Außen (numerisch) aufsteigend, bei Gleichstand innen aufsteigend.
  - Bei mehreren Treffern: wähle die oberste (kleinste Außen, dann kleinste Innen).
- Falls **kein** Eintrag ausreicht: gibt den kleinsten erforderlichen cetta-Wert aus und meldet
  "bei kleinster möglicher außen: keiner".
- Ausgabe:
  - Ein zusammengefasster String wie "22x1 cetta 2.60" (basierend auf Außen x Innen und berechnetem cetta),
    sowie Hinweise, welcher Datensatz gewählt wurde oder dass keiner reicht.

CSV-Annahme:
- Trennzeichen = "," (Komma)
- Dezimaltrennzeichen = "." (Punkt)
- Spalten: außen, innen, cetta_max, cetta_pro_meter
  Hinweis: außen/innen als Zahlen, cetta_* als Zahlen

Hinweis zur Toleranz beim Parsen:
- Erlaubt Leerzeichen; akzeptiert Eingaben wie "80,034" und wandelt Komma->Punkt.

Autor: ChatGPT
Lizenz: MIT
"""
import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import List, Optional
from PIL import Image, ImageTk
import tkinter.font as tkfont

# Windows High-DPI Awareness (macht UI größer/schärfer auf hochauflösenden Displays)
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")

@dataclass
class EntryRow:
    label: str        # z.B. "22x1" aus CSV
    innen: float
    cetta_max: float
    cetta_pro_meter: float

    def key(self):
        return (self.aussen, self.innen)


def list_types() -> List[str]:
    """Listet alle CSV-Dateien im db-Ordner und gibt Namen ohne Endung zurück."""
    if not os.path.isdir(DB_DIR):
        return []
    names = []
    for fn in os.listdir(DB_DIR):
        if fn.lower().endswith(".csv"):
            names.append(os.path.splitext(fn)[0])
    names.sort()
    return names

def load_type_rows(type_name: str) -> List[EntryRow]:
    """Lädt die CSV eines Typs und gibt geparste Zeilen zurück (Reihenfolge bleibt erhalten)."""
    path = os.path.join(DB_DIR, f"{type_name}.csv")
    rows: List[EntryRow] = []
    if not os.path.isfile(path):
        return rows

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")

        # Header normalisieren
        def norm(s: str) -> str:
            return s.strip().lower().replace(" ", "")

        header_map = {norm(h): h for h in reader.fieldnames or []}

        def get(row, logical):
            # logical in {"außen","innen","cetta_max","cetta_pro_meter"}
            for candidate in [logical, logical.replace("ß", "ss"), logical.replace("_", "")]:
                if candidate in header_map:
                    return row[header_map[candidate]]
                if candidate.replace("außen", "aussen") in header_map:
                    return row[header_map[candidate.replace("außen", "aussen")]]
            # Fallback: Suche Teilstring
            for k, v in header_map.items():
                if logical.replace("_", "") in k:
                    return row[v]
            raise KeyError(
                f"Spalte '{logical}' nicht gefunden. Vorhandene: {list(header_map.values())}"
            )

        for i, row in enumerate(reader, start=2):  # Start=2, da Header in Zeile 1
            try:
                label = str(get(row, "außen")).strip()
                innen = float(str(get(row, "innen")).strip().replace(",", "."))
                cetta_max = float(str(get(row, "cetta_max")).strip().replace(",", "."))
                cetta_pm = float(str(get(row, "cetta_pro_meter")).strip().replace(",", "."))
                rows.append(EntryRow(label, innen, cetta_max, cetta_pm))

            except Exception as e:
                print(f"[WARN] Fehler beim Parsen in {path}, Zeile {i}: {e} | Daten: {row}")
                continue

    return rows


def parse_length_to_meters(text: str, unit: str) -> Optional[float]:
    """Parst einen Längentext (akzeptiert , oder .) und rechnet nach Meter um."""
    if not text:
        return None
    try:
        val = float(text.replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if unit == "m":
        return val
    elif unit == "cm":
        return val / 100.0
    else:
        return None


def select_best(rows: List[EntryRow], length_m: float) -> dict:
    """Wählt die passende Zeile entsprechend der Anforderungen.
    Rückgabe-Dict:
      {
        'status': 'ok' | 'none',
        'row': EntryRow | None,
        'required_cetta': float,
        'message': str
      }
    Logik: required_cetta = length_m * row.cetta_pro_meter (zeilenabhängig bei Anzeige),
    Auswahl: erste Zeile (nach aussen, innen sortiert) mit row.cetta_max >= required_cetta.
    Wenn keine: status='none'.
    """
    if not rows:
        return {"status": "none", "row": None, "required_cetta": 0.0, "message": "Keine Datenzeilen vorhanden."}

    # Prüfe nacheinander: Für die Auswahl benötigen wir required_cetta abhängig von der Zeile?
    # Achtung: In der Aufgabenbeschreibung wird required_cetta = L * cetta_pro_meter berechnet,
    # dann eine Zeile gesucht, deren cetta_max >= required_cetta. Da cetta_pro_meter je Zeile variieren kann,
    # müssen wir für jede Zeile prüfen, ob sie den Bedarf deckt. Wir wählen die erste (kleinste Außen) die passt.

    # Wir merken uns für die Ausgabe auch die required_cetta der gewählten Zeile.
    chosen: Optional[EntryRow] = None
    chosen_required: float = 0.0

    for r in rows:
        req = length_m * r.cetta_pro_meter
        if r.cetta_max + 1e-12 >= req:  # kleine Toleranz
            chosen = r
            chosen_required = req
            break

    if chosen is not None:
        return {
            "status": "ok",
            "row": chosen,
            "required_cetta": chosen_required,
            "message": "OK"
        }

    # Kein Eintrag reicht aus
    # Vorgabe: "den kleinsten cetta wert ausgeben und sagen bei kleinster möglicher außen keiner"
    # Interpretation: Wir geben den (für die kleinste Außen-Zeile) errechneten Bedarf aus und melden, dass bei kleinster Außen keiner passt.
    smallest = rows[0]
    req_smallest = length_m * smallest.cetta_pro_meter
    return {
        "status": "none",
        "row": smallest,
        "required_cetta": req_smallest,
        "message": "Bei kleinster möglicher Außen: keiner (kein Eintrag deckt den Bedarf)"
    }



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("The Quick Abblaseleitungs Calculator")
        self.geometry("1280x900")   # groß genug

        # --- 1) DPI ermitteln und tk-scaling passend setzen ---
        # Tk skaliert Punkte -> Pixel. 1 Punkt = 1/72 Zoll.
        # Wir messen echte DPI und setzen scaling = DPI/72 * Faktor.
        dpi = self.winfo_fpixels('1i')  # Pixel pro Inch
        base_scaling = dpi / 72.0
        user_factor = 1.25              # optionaler Zusatzzoom (1.25–1.6 je nach Geschmack)
        self.tk.call("tk", "scaling", base_scaling * user_factor)

        # --- 2) Named Fonts groß & plattformneutral setzen ---
        import tkinter.font as tkfont
        def bump(name, size, **kw):
            f = tkfont.nametofont(name)
            f.configure(size=size, **kw)
            # Wichtig: Option-DB, damit ttk-Widgets den Font auch nutzen
            self.option_add(f"*{name}", f)

        # Standard-Fonts hochziehen (nutze System-Familie; KEINE feste 'Segoe UI'!)
        bump("TkDefaultFont", 16)
        bump("TkTextFont",    16)
        bump("TkFixedFont",   15)
        bump("TkMenuFont",    16)
        bump("TkHeadingFont", 20, weight="bold")
        try:
            bump("TkIconFont",    16)
            bump("TkTooltipFont", 14)
        except Exception:
            pass  # ältere Tk-Versionen kennen diese evtl. nicht

        # Combobox-Popdown (Listbox im Popdown-Fenster) separat größer setzen:
        # (ttk Combobox nutzt für die DropDown-Liste nicht automatisch TkDefaultFont)
        textfam = tkfont.nametofont("TkTextFont").actual("family")
        textsz  = tkfont.nametofont("TkTextFont").actual("size")
        self.option_add("*TCombobox*Listbox.font", f"{textfam} {textsz}")

        # App-States
        self.types = list_types()
        self.selected_type = tk.StringVar(value=self.types[0] if self.types else "")
        self.length_text = tk.StringVar(value="")
        self.unit = tk.StringVar(value="m")

        self._apply_style()
        self._build_ui()

        



    
    def _build_ui(self):
        pad = 16
        frm = ttk.Frame(self, padding=pad)
        frm.pack(fill=tk.BOTH, expand=True)

        # Header
        header = ttk.Frame(frm)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, pad))
        header.columnconfigure(1, weight=1)

        try:
            logo_path = os.path.join(os.path.dirname(__file__), "logo.jpg")
            img = Image.open(logo_path).resize((96, 96))
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(header, image=self.logo_img).grid(row=0, column=0, padx=(0, pad))
        except Exception:
            ttk.Label(header, text="[Logo]").grid(row=0, column=0, padx=(0, pad))

        # Titel nutzt TkHeadingFont automatisch
        ttk.Label(header, text="The Quick Abblaseleitungs Calculator").grid(row=0, column=1, sticky="w")

        # Typ
        ttk.Label(frm, text="Typ (CSV):").grid(row=1, column=0, sticky="w", padx=pad, pady=(pad, 4))
        self.cb_type = ttk.Combobox(frm, values=self.types, textvariable=self.selected_type, state="readonly")
        self.cb_type.grid(row=1, column=1, sticky="ew", padx=pad, pady=(pad, 4))

        # Länge
        ttk.Label(frm, text="Länge:").grid(row=2, column=0, sticky="w", padx=pad, pady=4)
        self.ent_len = ttk.Entry(frm, textvariable=self.length_text)
        self.ent_len.grid(row=2, column=1, sticky="ew", padx=pad, pady=4)
        self.cb_unit = ttk.Combobox(frm, values=["m", "cm"], textvariable=self.unit, state="readonly", width=6)
        self.cb_unit.grid(row=2, column=2, sticky="w", padx=pad, pady=4)

        # Button
        self.btn_calc = ttk.Button(frm, text="💡 Berechnen", command=self.on_calculate)
        self.btn_calc.grid(row=3, column=1, sticky="e", padx=pad, pady=12)

        ttk.Separator(frm).grid(row=4, column=0, columnspan=3, sticky="ew", padx=pad, pady=(4, 8))

        ttk.Label(frm, text="Ergebnis:").grid(row=5, column=0, sticky="w", padx=pad)
        self.lbl_summary = ttk.Label(frm, text="–", justify="left")
        self.lbl_summary.grid(row=6, column=0, columnspan=3, sticky="w", padx=pad, pady=(4, 2))
        self.lbl_detail = ttk.Label(frm, text="", justify="left")
        self.lbl_detail.grid(row=7, column=0, columnspan=3, sticky="w", padx=pad)

        frm.columnconfigure(1, weight=1)


    def on_calculate(self):
        type_name = self.selected_type.get().strip()
        if not type_name:
            messagebox.showerror("Fehler", "Bitte einen Typ auswählen (CSV im Ordner 'db').")
            return

        length_m = parse_length_to_meters(self.length_text.get(), self.unit.get())
        if length_m is None or length_m <= 0:
            messagebox.showerror("Fehler", "Bitte eine gültige Länge eingeben (z. B. 80,034).")
            return

        rows = load_type_rows(type_name)
        if not rows:
            messagebox.showerror("Fehler", f"Keine Daten in '{type_name}.csv' gefunden oder Spaltennamen fehlen.")
            return

        result = select_best(rows, length_m)

        if result["status"] == "ok":
            r = result["row"]
            req = result["required_cetta"]
            # label direkt aus CSV, z.B. "22x1"
            summary = f"Auswahl: {r.label} cetta {req:.3f}"
            detail = (
                f"Gefundener Datensatz (oberste passende Zeile):\n"
                f"  eintrag={r.label}, innen={r.innen}, "
                f"cetta_max={r.cetta_max}, cetta_pro_meter={r.cetta_pro_meter}"
            )
            self.lbl_summary.config(text=summary)
            self.lbl_detail.config(text=detail)
        else:
            r = result["row"]  # oberste Zeile zur Referenz
            req = result["required_cetta"]
            summary = f"{result['message']}. Erforderliche cetta (bei oberster Zeile): {req:.3f}"
            detail = (
                f"Oberste Zeile war: {r.label} | "
                f"cetta_max={r.cetta_max}, cetta_pro_meter={r.cetta_pro_meter}"
            )
            self.lbl_summary.config(text=summary)
            self.lbl_detail.config(text=detail)

    def _apply_style(self):
        accent = "#00bcd4"   # Türkis
        bg = "#ffffff"       # Weiß
        fg = "#222222"

        style = ttk.Style(self)
        style.theme_use("clam")

        # Grundfarben & Abstände
        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)

        style.configure(
            "TButton",
            background=accent,
            foreground="white",
            padding=12,
            relief="flat",
            borderwidth=0
        )
        style.map(
            "TButton",
            background=[("active", "#0097a7")],
            relief=[("pressed", "sunken")]
        )

        style.configure(
            "TEntry",
            fieldbackground="#f7f7f7",
            padding=10,
            relief="flat"
        )
        style.configure(
            "TCombobox",
            fieldbackground="#f7f7f7",
            background=bg,
            padding=8
        )

if __name__ == "__main__":
    app = App()
    app.mainloop()
