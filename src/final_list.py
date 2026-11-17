#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vypocet konecneho seznamu postupujicich - spolecny pro finalni export
(generate_final_export.py) i zalozku na webu (generate_presentation.py).

- bere radky s Postupuje = ANO z results-for-excel.csv
- aplikuje rucni upravy z rucni-upravy.txt (PRESUN / PRIDAT / ODEBRAT)
- vynecha Open a neoficialni kategorie
- seradi KATA -> KUMITE, podle veku, pohlavi a vahy
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from config import EXCEL_CSV, MANUAL_EDITS_FILE
from generate_presentation import (
    build_official_display_categories,
    load_csv_rows,
    official_category_keys,
)
from manual_edits import load_manual_edits, split_comment
from qualification import is_ano_value
from utils import bez_diakritiky, normalizuj


DISCIPLINE_ORDER = {
    "KATA": 0,
    "KUMITE": 1,
}



def _row_from_csv(row: dict) -> dict:
    return {
        "_sort_poradi": row.get("Pořadí", row.get("Poradi", "")),
        "Kategorie": row.get("Kategorie", ""),
        "Jmeno": row.get("Jméno", row.get("Jmeno", "")),
        "Prijmeni": row.get("Příjmení", row.get("Prijmeni", "")),
        "Klub": row.get("Klub", ""),
    }


def is_open_category(category: str) -> bool:
    return "open" in _norm(category).replace("-", " ").split()


def _norm(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _full_name(row: dict) -> str:
    return _norm(f"{row['Jmeno']} {row['Prijmeni']}")


# Poradi vekovych skupin ve finalnim exportu (od nejmladsich)
AGE_GROUPS = [
    ("u8",),
    ("u10",),
    ("u11",),
    ("u12",),
    ("u13",),
    ("u14",),
    ("dorostenci", "dorostenky"),
    ("juniori", "juniorky"),
    ("u21",),
    ("muzi", "zeny"),
    ("masters",),
]

GENDER_FIRST = {"chlapci", "dorostenci", "juniori", "muzi"}
GENDER_SECOND = {"divky", "dorostenky", "juniorky", "zeny"}


def final_category_sort_key(category: str) -> tuple:
    """Finalni vystup: KATA pred KUMITE, pak podle veku (U10 -> Uxx), pohlavi a vahy."""
    tokens = bez_diakritiky(category).casefold().split()
    discipline = tokens[0].upper() if tokens else ""

    age_order = 999
    if "masters" in tokens:
        age_order = next(i for i, g in enumerate(AGE_GROUPS) if "masters" in g)
    else:
        for i, group in enumerate(AGE_GROUPS):
            if any(token in tokens for token in group):
                age_order = i
                break

    gender_order = 999
    for token in tokens:
        if token in GENDER_FIRST:
            gender_order = 0
            break
        if token in GENDER_SECOND:
            gender_order = 1
            break

    weight_order = (0, 0)
    for token in tokens:
        raw = token.replace("kg", "")
        if raw.startswith(("-", "+")) and raw[1:].isdigit():
            weight_order = (1 if raw[0] == "+" else 0, int(raw[1:]))
            break

    return (
        DISCIPLINE_ORDER.get(discipline, 999),
        age_order,
        gender_order,
        weight_order,
        category,
    )


def _split_name(full_name: str) -> tuple:
    parts = full_name.split()
    return " ".join(parts[:-1]), parts[-1]


def apply_manual_edits(
    filtered: List[dict], all_rows: List[dict], edits: List[tuple], source: Path
) -> List[str]:
    """Aplikuje rucni upravy na seznam postupujicich. Vraci seznam chyb."""
    errors: List[str] = []
    known_categories = {_norm(r.get("Kategorie", "")): r.get("Kategorie", "") for r in all_rows}
    expected = {"PRESUN": 3, "PRIDAT": 3, "ODEBRAT": 2, "PRESTUP": 3}

    def err(line_no: int, raw: str, msg: str) -> None:
        errors.append(f"{source.name}:{line_no}: {msg}\n    {raw}")

    def find(name: str, category: str) -> List[dict]:
        return [r for r in filtered if _full_name(r) == _norm(name) and _norm(r["Kategorie"]) == _norm(category)]

    def check_category(line_no: int, raw: str, category: str) -> str | None:
        canonical = known_categories.get(_norm(category))
        if canonical is None:
            err(line_no, raw, f"kategorie neexistuje ve vysledcich: {category}")
        return canonical

    for line_no, action, fields, raw in edits:
        if action not in expected:
            err(line_no, raw, f"neznama akce '{action}' (PRESUN / PRIDAT / ODEBRAT)")
            continue
        if len(fields) != expected[action] or not all(fields):
            err(line_no, raw, f"{action} ocekava {expected[action]} pole oddelena '|'")
            continue

        if action == "PRESTUP":
            # klub uz zmenila agregace vysledku - tady jen oznacit radky
            name, old_club, new_club = fields
            for row in filtered:
                if _full_name(row) == _norm(name) and not row.get("Uprava"):
                    row["Uprava"] = "prestup"
                    row["Prestup_z"] = old_club
            print(f"Rucni uprava: {raw}")
            continue

        if action == "PRESUN":
            name, old_cat, new_cat = fields
            matches = find(name, old_cat)
            target = check_category(line_no, raw, new_cat)
            if not matches:
                err(line_no, raw, f"'{name}' neni mezi postupujicimi v kategorii '{old_cat}'")
                continue
            if target is None:
                continue
            if find(name, target):
                err(line_no, raw, f"'{name}' uz je mezi postupujicimi v '{target}'")
                continue
            for row in matches:
                row["Kategorie"] = target
                row["_sort_poradi"] = ""  # rucne presunuti na konec kategorie
                row["Uprava"] = "presun"

        elif action == "PRIDAT":
            name, category, club = fields
            target = check_category(line_no, raw, category)
            if target is None:
                continue
            if find(name, target):
                err(line_no, raw, f"'{name}' uz je mezi postupujicimi v '{target}'")
                continue
            jmeno, prijmeni = _split_name(name)
            filtered.append({"_sort_poradi": "", "Kategorie": target, "Jmeno": jmeno, "Prijmeni": prijmeni, "Klub": club, "Uprava": "pridat"})

        elif action == "ODEBRAT":
            name, category = fields
            matches = find(name, category)
            if not matches:
                err(line_no, raw, f"'{name}' neni mezi postupujicimi v kategorii '{category}'")
                continue
            for row in matches:
                filtered.remove(row)

        print(f"Rucni uprava: {raw}")

    return errors


def filter_postupujici(
    header: List[str],
    rows: List[dict],
    manual_edits: List[tuple] | None = None,
    manual_source: Path = MANUAL_EDITS_FILE,
) -> tuple:
    filtered: List[dict] = [
        _row_from_csv(row) for row in rows if is_ano_value(row.get("Postupuje", "NE"))
    ]
    errors = apply_manual_edits(filtered, rows, manual_edits or [], manual_source)
    # Open kategorie (mimo predpis) do finalniho exportu nepatri
    filtered = [row for row in filtered if not is_open_category(row["Kategorie"])]
    # Jen oficialni kategorie CSKe (dle predpisu MCR)
    official_keys = official_category_keys(build_official_display_categories())
    skipped = sorted({row["Kategorie"] for row in filtered if normalizuj(row["Kategorie"]) not in official_keys})
    for category in skipped:
        print(f"Vynechano (neoficialni kategorie): {category}")
    filtered = [row for row in filtered if normalizuj(row["Kategorie"]) in official_keys]
    filtered.sort(
        key=lambda row: (
            final_category_sort_key(row["Kategorie"]),
            int(str(row["_sort_poradi"]).replace(".", "") or "9999"),
            row["Prijmeni"],
            row["Jmeno"],
        )
    )
    for row in filtered:
        row.pop("_sort_poradi", None)
    return filtered, errors


def compute_final_list(
    csv_path: Path = EXCEL_CSV,
    manual_path: Path = MANUAL_EDITS_FILE,
) -> tuple:
    """Vrati (serazene radky postupujicich, chyby v rucnich upravach)."""
    header, rows = load_csv_rows(csv_path)
    edits = load_manual_edits(manual_path)
    return filter_postupujici(header, rows, edits, manual_path)


MANUAL_EDIT_LABELS = {
    "PRESUN": "Přesun",
    "PRIDAT": "Doplnění",
    "ODEBRAT": "Vyřazení",
    "PRESTUP": "Přestup",
}

def describe_manual_edits(
    csv_path: Path = EXCEL_CSV,
    manual_path: Path = MANUAL_EDITS_FILE,
) -> List[dict]:
    """Rucni upravy pro zobrazeni na webu: typ, zavodnik, klub, zmena, duvod, datum."""
    _header, rows = load_csv_rows(csv_path)
    clubs_by_name = {}
    for row in rows:
        full = _norm(f"{row.get('Jméno', '')} {row.get('Příjmení', '')}")
        clubs_by_name.setdefault(full, row.get("Klub", ""))

    items: List[dict] = []
    for _line_no, action, fields, raw in load_manual_edits(manual_path):
        if action not in MANUAL_EDIT_LABELS or not fields:
            continue
        comment, date = split_comment(raw)
        name = fields[0]
        item = {
            "akce": action,
            "typ": MANUAL_EDIT_LABELS[action],
            "zavodnik": name,
            "klub": clubs_by_name.get(_norm(name), ""),
            "z": "",
            "do": "",
            "duvod": comment,
            "datum": date,
        }
        if action == "PRESUN" and len(fields) >= 3:
            item["z"], item["do"] = fields[1], fields[2]
        elif action == "PRIDAT" and len(fields) >= 3:
            item["do"], item["klub"] = fields[1], fields[2]
        elif action == "ODEBRAT" and len(fields) >= 2:
            item["z"] = fields[1]
        elif action == "PRESTUP" and len(fields) >= 3:
            item["z"], item["do"] = fields[1], fields[2]
            item["klub"] = fields[2]
        items.append(item)
    return items
