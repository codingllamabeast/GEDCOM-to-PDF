#!/usr/bin/env python3
"""
GEDCOM to PDF Family Tree Converter
-----------------------------------

A Python GUI tool to load a GEDCOM genealogy file, select the number of
generations based on user input, and output a cleanly 
formatted family tree report as a PDF document.

Features:
- File picker for GEDCOM input
- Combobox for selecting generations (2-10 are allowed)
- Save As dialog for PDF output
- Responsive window that scales with resizing
- Outputs structured family tree with separators
- Missing values displayed as "No data"

Dependencies:
- tkinter
- reportlab
"""



import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from collections import defaultdict
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

SEP_LINE = "-" * 119  # long separator for generations
SEP_SHORT = "-------------"     # short separator for individuals


# ----------------------------
# GEDCOM Parsing
# ----------------------------
def clean_id(record_id: str) -> str:
    """Remove surrounding '@' from a GEDCOM ID."""
    return record_id.strip("@") if record_id else record_id


def parse_gedcom(path):
    """
    Parse a GEDCOM file into people, families, and sources dictionaries.
    Returns (people, families, sources, root_id).
    """
    people, families, sources = {}, {}, {}
    root_id = None
    current, current_type = None, None
    in_birth = in_death = in_marr = False

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(" ", 2)
            if len(parts) < 2:
                continue
            level, tag = parts[0], parts[1]
            data = parts[2] if len(parts) > 2 else ""

            # New record start
            if level == "0":
                if tag.startswith("@"):
                    rec_id = clean_id(tag)
                    rec_type = data
                    if rec_type == "INDI":
                        current, current_type = rec_id, "INDI"
                        if root_id is None:
                            root_id = current
                        people[current] = {"id": current, "name": "", "events": {},
                                           "sources": [], "famc": [], "fams": []}
                    elif rec_type == "FAM":
                        current, current_type = rec_id, "FAM"
                        families[current] = {"id": current, "husb": "", "wife": "",
                                             "chil": [], "events": {}}
                    elif rec_type == "SOUR":
                        current, current_type = rec_id, "SOUR"
                        sources[current] = {"id": rec_id, "title": "", "author": "",
                                            "publ": "", "text": ""}
                    else:
                        current = current_type = None
                else:
                    current = current_type = None
                in_birth = in_death = in_marr = False
                continue

            # Individual
            if current_type == "INDI":
                if tag == "NAME":
                    people[current]["name"] = data.replace("/", "").strip()
                elif tag == "BIRT":
                    in_birth = True
                elif tag == "DEAT":
                    in_death = True
                elif tag == "FAMC":
                    people[current]["famc"].append(clean_id(data))
                elif tag == "FAMS":
                    people[current]["fams"].append(clean_id(data))
                elif tag == "SOUR":
                    people[current]["sources"].append(clean_id(data))
                elif tag == "DATE":
                    if in_birth:
                        people[current]["events"]["birth_date"] = data
                        in_birth = False
                    elif in_death:
                        people[current]["events"]["death_date"] = data
                        in_death = False
                elif tag == "PLAC":
                    if "birth_date" in people[current]["events"] and "birth_place" not in people[current]["events"]:
                        people[current]["events"]["birth_place"] = data
                    elif "death_date" in people[current]["events"] and "death_place" not in people[current]["events"]:
                        people[current]["events"]["death_place"] = data

            # Family
            elif current_type == "FAM":
                if tag == "HUSB":
                    families[current]["husb"] = clean_id(data)
                elif tag == "WIFE":
                    families[current]["wife"] = clean_id(data)
                elif tag == "CHIL":
                    families[current]["chil"].append(clean_id(data))
                elif tag == "MARR":
                    in_marr = True
                elif tag == "DATE" and in_marr:
                    families[current]["events"]["marriage_date"] = data
                    in_marr = False
                elif tag == "PLAC":
                    if "marriage_date" in families[current]["events"] and "marriage_place" not in families[current]["events"]:
                        families[current]["events"]["marriage_place"] = data

            # Source
            elif current_type == "SOUR":
                if tag == "TITL":
                    sources[current]["title"] = data
                elif tag == "AUTH":
                    sources[current]["author"] = data
                elif tag == "PUBL":
                    sources[current]["publ"] = data
                elif tag == "TEXT":
                    sources[current]["text"] = data

    return people, families, sources, root_id


def build_generations(people, families, root_id, max_gen=6):
    """
    Build a dict of generations from a root person.
    gens[1] = root person, gens[2] = parents and so on
    """
    generations = defaultdict(list)
    generations[1] = [root_id]
    for g in range(2, max_gen + 1):
        current = []
        for person_id in generations[g - 1]:
            if person_id not in people:
                continue
            for fam_id in people[person_id]["famc"]:
                fam = families.get(fam_id)
                if fam:
                    if fam["husb"]:
                        current.append(fam["husb"])
                    if fam["wife"]:
                        current.append(fam["wife"])
        if not current:
            break
        generations[g] = current
    return generations


def pretty_marriage(family):
    """Format marriage event if available, else return 'No data'."""
    if not family:
        return "No data"
    date = family["events"].get("marriage_date", "")
    place = family["events"].get("marriage_place", "")
    if date and place:
        return f"{date} — {place}"
    return date or place or "No data"


def generation_title(gen_number: int) -> str:
    """Return human-readable generation title with relationship label."""
    labels = {
        1: "Generation 1",
        2: "Generation 2 (Parents)",
        3: "Generation 3 (Grandparents)",
        4: "Generation 4 (Great-grandparents)",
        5: "Generation 5 (2nd Great-grandparents)",
        6: "Generation 6 (3rd Great-grandparents)",
        7: "Generation 7 (4th Great-grandparents)",
        8: "Generation 8 (5th Great-grandparents)",
        9: "Generation 9 (6th Great-grandparents)",
        10: "Generation 10 (7th Great-grandparents)",
    }
    return labels.get(gen_number, f"Generation {gen_number}")


# ----------------------------
# PDF Writer
# ----------------------------
def write_generations_pdf(pdf_path, people, families, sources, generations):
    """
    Write parsed family tree generations to a PDF file.
    Includes long separators for each generation and shorter ones
    between individuals.
    """
    styles = getSampleStyleSheet()
    elements = []
    max_actual = max(generations.keys())

    def safe(val):
        """Return value or 'No data' if empty."""
        return val if val else "No data"

    for g in sorted(generations.keys()):
        title = generation_title(g)
        elements.append(Paragraph(title, styles["Heading2"]))
        elements.append(Paragraph(SEP_LINE, styles["Normal"]))

        for i, person_id in enumerate(generations[g]):
            person = people.get(person_id, {"name": person_id, "events": {}})
            family = families[person["fams"][0]] if person.get("fams") else None

            lines = [
                f"Name: {safe(person.get('name', ''))}",
                f"Birth: {safe(person['events'].get('birth_date', ''))}",
                f"Birthplace: {safe(person['events'].get('birth_place', ''))}",
                f"Marriage: {pretty_marriage(family)}"
            ]
            if g > 1:
                lines.append(f"Death: {safe(person['events'].get('death_date', ''))}")
                lines.append(f"Deathplace: {safe(person['events'].get('death_place', ''))}")
                if person.get("sources"):
                    srcs = [sources[s]["title"] for s in person["sources"] if s in sources]
                    lines.append("Sources: " + "; ".join(srcs))
                else:
                    lines.append("Sources: No data")

            for line in lines:
                elements.append(Paragraph(line, styles["Normal"]))
            elements.append(Spacer(1, 12))

            if i < len(generations[g]) - 1:
                elements.append(Paragraph(SEP_SHORT, styles["Normal"]))
                elements.append(Spacer(1, 12))

        elements.append(Paragraph(SEP_LINE, styles["Normal"]))
        elements.append(Spacer(1, 20))

    doc = SimpleDocTemplate(pdf_path)
    doc.build(elements)
    return max_actual


# ----------------------------
# GUI
# ----------------------------
def run_gui():
    """Launch the tkinter GUI for selecting GEDCOM, generations, and saving PDF."""
    def choose_file():
        filepath = filedialog.askopenfilename(
            filetypes=[("GEDCOM files", "*.ged")],
            initialdir=os.path.expanduser("~")
        )
        if filepath:
            entry_file.delete(0, tk.END)
            entry_file.insert(0, filepath)

    def generate():
        ged_path = entry_file.get()
        if not ged_path:
            messagebox.showerror("Error", "Please select a GEDCOM file first.")
            return

        try:
            requested_gens = int(combo_gen.get())
            if requested_gens < 2 or requested_gens > 10:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Input", "Generations must be between 2 and 10.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialdir=os.path.expanduser("~"),
            title="Save As"
        )
        if not save_path:
            return

        try:
            people, families, sources, root_id = parse_gedcom(ged_path)
            if not root_id:
                messagebox.showerror("Error", "No root person found in GEDCOM.")
                return

            generations = build_generations(people, families, root_id, requested_gens)
            max_actual = write_generations_pdf(save_path, people, families, sources, generations)

            if requested_gens > max_actual:
                messagebox.showinfo(
                    "Notice",
                    f"This tree does not contain members in Generation {requested_gens}. "
                    f"Maximum of {max_actual} generations generated.\nPDF saved as {save_path}"
                )
            else:
                messagebox.showinfo("Done", f"PDF generated at:\n{save_path}")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    root = tk.Tk()
    root.title("GEDCOM to PDF Family Tree")
    root.geometry("600x300")  # default window size

    # make layout responsive
    for i in range(3):
        root.rowconfigure(i, weight=1)
    for j in range(3):
        root.columnconfigure(j, weight=1)

    tk.Label(root, text="GEDCOM File:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    entry_file = tk.Entry(root)
    entry_file.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
    tk.Button(root, text="Browse", command=choose_file).grid(row=0, column=2, padx=5, pady=5)

    tk.Label(root, text="Generations:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    combo_gen = ttk.Combobox(root, values=list(range(2, 11)))
    combo_gen.set("6")
    combo_gen.grid(row=1, column=1, sticky="w", padx=5, pady=5)

    tk.Button(root, text="Generate PDF", command=generate).grid(row=2, column=1, pady=10)

    root.mainloop()


if __name__ == "__main__":
    run_gui()
