#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Referencni predpis kategorii CSKe (kata / kumite jednotlivci i tymy).

Ucel: dokumentace oficialnich vekovych a hmotnostnich kategorii.
Zatim NEPOUZITO v pipeline (validate / fix / aggregate / postup) - jen info.

Nazvy v `label` odpovidaji typickym retezcum v XML (kategorie1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgeCategory:
    """Vekova kategorie."""

    label: str
    age_from: int
    age_to: Optional[int]  # None = bez horni meze
    note: str = ""


@dataclass(frozen=True)
class WeightCategory:
    """Hmotnostni kategorie + casovy limit zapasu (kumite)."""

    age_label: str
    weights: tuple[str, ...]
    match_minutes: float
    note: str = ""


# ---------------------------------------------------------------------------
# (1) KATA jednotlivci - vekove kategorie
# ---------------------------------------------------------------------------
KATA_INDIVIDUAL: tuple[AgeCategory, ...] = (
    AgeCategory("Masters muži 60+", 60, None),
    AgeCategory("Masters ženy 55+", 55, None),
    AgeCategory("Masters muži U60", 50, 59),
    AgeCategory("Masters ženy U55", 45, 54),
    AgeCategory("Masters muži U50", 40, 49),
    AgeCategory("Masters ženy U45", 35, 44),
    AgeCategory("muži", 16, None, "senioři"),
    AgeCategory("ženy", 16, None, "seniorky"),
    AgeCategory("muži U21", 18, 20),
    AgeCategory("ženy U21", 18, 20),
    AgeCategory("junioři", 16, 17),
    AgeCategory("juniorky", 16, 17),
    AgeCategory("dorostenci", 14, 15),
    AgeCategory("dorostenky", 14, 15),
    AgeCategory("chlapci U14", 13, 13),
    AgeCategory("dívky U14", 13, 13),
    AgeCategory("chlapci U13", 12, 12),
    AgeCategory("dívky U13", 12, 12),
    AgeCategory("chlapci U12", 11, 11),
    AgeCategory("dívky U12", 11, 11),
    AgeCategory("chlapci U11", 10, 10),
    AgeCategory("dívky U11", 10, 10),
    AgeCategory("chlapci U10", 7, 9),
    AgeCategory("dívky U10", 7, 9),
)

# ---------------------------------------------------------------------------
# (2) KUMITE jednotlivci - vekove kategorie
# ---------------------------------------------------------------------------
KUMITE_INDIVIDUAL: tuple[AgeCategory, ...] = (
    AgeCategory("Masters muži 50+", 50, None),
    AgeCategory("Masters ženy 45+", 45, None),
    AgeCategory("Masters muži U50", 40, 49),
    AgeCategory("Masters ženy U45", 35, 44),
    AgeCategory("muži", 18, None, "senioři"),
    AgeCategory("ženy", 18, None, "seniorky"),
    AgeCategory("muži U21", 18, 20),
    AgeCategory("ženy U21", 18, 20),
    AgeCategory("junioři", 16, 17),
    AgeCategory("juniorky", 16, 17),
    AgeCategory("dorostenci", 14, 15),
    AgeCategory("dorostenky", 14, 15),
    AgeCategory("chlapci U14", 12, 13),
    AgeCategory("dívky U14", 12, 13),
    AgeCategory("chlapci U12", 10, 11),
    AgeCategory("dívky U12", 10, 11),
    AgeCategory("chlapci U10", 7, 9, "v predpisu i jako 'chlapci 10'"),
    AgeCategory("dívky U10", 7, 9),
)

# ---------------------------------------------------------------------------
# (3) KATA tym - vekove kategorie
# ---------------------------------------------------------------------------
KATA_TEAM: tuple[AgeCategory, ...] = (
    AgeCategory("muži", 16, None, "senioři"),
    AgeCategory("ženy", 16, None, "seniorky"),
    AgeCategory("junioři", 14, 17),
    AgeCategory("juniorky", 14, 17),
    AgeCategory("chlapci U14", 11, 13),
    AgeCategory("dívky U14", 11, 13),
    AgeCategory("chlapci U11", 7, 10),
    AgeCategory("dívky U11", 7, 10),
)

# ---------------------------------------------------------------------------
# (4) KUMITE tym - vekove kategorie
# ---------------------------------------------------------------------------
KUMITE_TEAM: tuple[AgeCategory, ...] = (
    AgeCategory("muži", 18, None, "senioři"),
    AgeCategory("ženy", 18, None, "seniorky"),
    AgeCategory("junioři", 16, 17),
    AgeCategory("juniorky", 16, 17),
    AgeCategory("dorostenci", 14, 15),
    AgeCategory("dorostenky", 14, 15),
    AgeCategory("chlapci U14", 12, 13),
    AgeCategory("dívky U14", 12, 13),
)

# ---------------------------------------------------------------------------
# (5) KUMITE - hmotnostni kategorie + casove limity zapasu
# ---------------------------------------------------------------------------
KUMITE_WEIGHTS: tuple[WeightCategory, ...] = (
    WeightCategory("Masters muži U50 / 50+", ("BRH",), 2.0),
    WeightCategory("Masters ženy U45 / 45+", ("BRH",), 2.0),
    WeightCategory(
        "muži",
        ("-67 kg", "-75 kg", "-84 kg", "+84 kg"),
        3.0,
        "MČR skupiny: 2 minuty",
    ),
    WeightCategory(
        "ženy",
        ("-55 kg", "-61 kg", "-68 kg", "+68 kg"),
        3.0,
        "MČR skupiny: 2 minuty",
    ),
    WeightCategory("muži U21", ("-67 kg", "-75 kg", "+75 kg"), 2.0),
    WeightCategory("ženy U21", ("-61 kg", "+61 kg"), 2.0),
    WeightCategory("junioři", ("-61 kg", "-68 kg", "-76 kg", "+76 kg"), 2.0),
    WeightCategory("juniorky", ("-53 kg", "-59 kg", "-66 kg", "+66 kg"), 2.0),
    WeightCategory(
        "dorostenci",
        ("-52 kg", "-57 kg", "-63 kg", "-70 kg", "+70 kg"),
        2.0,
    ),
    WeightCategory("dorostenky", ("-47 kg", "-54 kg", "-61 kg", "+61 kg"), 2.0),
    WeightCategory(
        "chlapci U14",
        ("-40 kg", "-45 kg", "-50 kg", "-55 kg", "+55 kg"),
        1.5,
    ),
    WeightCategory(
        "dívky U14",
        ("-42 kg", "-47 kg", "-52 kg", "+52 kg"),
        1.5,
        "v predpisu i jako 'dívky 14'",
    ),
    WeightCategory(
        "chlapci U12",
        ("-30 kg", "-35 kg", "-40 kg", "-45 kg", "+45 kg"),
        1.5,
        "v predpisu i jako 'chlapci 12'",
    ),
    WeightCategory("dívky U12", ("-30 kg", "-35 kg", "-40 kg", "+40 kg"), 1.5),
    WeightCategory(
        "chlapci U10",
        ("-27 kg", "-32 kg", "+32 kg"),
        1.0,
        "v predpisu i jako 'chlapci 10'",
    ),
    WeightCategory("dívky U10", ("-30 kg", "+30 kg"), 1.0),
)


def format_age_range(cat: AgeCategory) -> str:
    """Lidsky citelny vekovy rozsah."""
    if cat.age_to is None:
        return f"{cat.age_from}+"
    if cat.age_from == cat.age_to:
        return f"{cat.age_from}"
    return f"{cat.age_from}-{cat.age_to}"


def print_summary() -> None:
    """Vypis predpisu na stdout (pro rychlou kontrolu)."""
    sections = (
        ("KATA jednotlivci", KATA_INDIVIDUAL),
        ("KUMITE jednotlivci", KUMITE_INDIVIDUAL),
        ("KATA tym", KATA_TEAM),
        ("KUMITE tym", KUMITE_TEAM),
    )
    for title, cats in sections:
        print(f"\n=== {title} ({len(cats)}) ===")
        for cat in cats:
            extra = f"  [{cat.note}]" if cat.note else ""
            print(f"  {cat.label:22} vek {format_age_range(cat):8}{extra}")

    print(f"\n=== KUMITE hmotnosti ({len(KUMITE_WEIGHTS)}) ===")
    for item in KUMITE_WEIGHTS:
        weights = ", ".join(item.weights)
        note = f"  ({item.note})" if item.note else ""
        print(f"  {item.age_label:28} {weights:40} {item.match_minutes} min{note}")


if __name__ == "__main__":
    print_summary()
