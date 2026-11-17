#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cteni rucnich uprav z rucni-upravy.txt (bez zavislosti na generatorech,
aby ho mohla pouzit i agregace vysledku).

Akce:
  PRESUN  | Jmeno Prijmeni | PUVODNI KATEGORIE | NOVA KATEGORIE   -> jen finalni seznam
  PRIDAT  | Jmeno Prijmeni | KATEGORIE | Klub                     -> jen finalni seznam
  ODEBRAT | Jmeno Prijmeni | KATEGORIE                            -> jen finalni seznam
  PRESTUP | Jmeno Prijmeni | PUVODNI KLUB | NOVY KLUB            -> uz pri agregaci
                                                                     (vysledky, nominace, web)
Text za # je komentar = duvod, na konci datum dd.mm.rrrr.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from config import MANUAL_EDITS_FILE

_DATE_RE = re.compile(r"[,;\s]*(\d{1,2}\.\s?\d{1,2}\.\s?\d{4})\s*$")


def norm_text(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def load_manual_edits(path: Path = MANUAL_EDITS_FILE) -> List[tuple]:
    """Nacte rucni-upravy.txt -> [(line_no, akce, [pole...], puvodni_radek)]."""
    if not path.is_file():
        return []
    edits = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split("|")]
        edits.append((line_no, fields[0].upper(), fields[1:], raw.strip()))
    return edits


def split_comment(raw: str) -> tuple:
    """Komentar radku -> (duvod, datum)."""
    comment = raw.split("#", 1)[1].strip() if "#" in raw else ""
    date = ""
    match = _DATE_RE.search(comment)
    if match:
        date = match.group(1).replace(" ", "")
        comment = comment[: match.start()].strip()
    return comment, date


def load_transfers(path: Path = MANUAL_EDITS_FILE) -> List[dict]:
    """PRESTUP radky -> [{line_no, raw, zavodnik, z, do, duvod, datum}]."""
    transfers = []
    for line_no, action, fields, raw in load_manual_edits(path):
        if action != "PRESTUP":
            continue
        if len(fields) != 3 or not all(fields):
            raise SystemExit(
                f"{path.name}:{line_no}: PRESTUP ocekava 3 pole oddelena '|'"
                f" (Jmeno Prijmeni | puvodni klub | novy klub)\n    {raw}"
            )
        reason, date = split_comment(raw)
        transfers.append({
            "line_no": line_no,
            "raw": raw,
            "zavodnik": fields[0],
            "z": fields[1],
            "do": fields[2],
            "duvod": reason,
            "datum": date,
        })
    return transfers
