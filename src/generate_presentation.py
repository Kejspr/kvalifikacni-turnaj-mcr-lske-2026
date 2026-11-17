#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML prezentace vysledku a nominaci.

Primarni zdroj tabulky: results-for-excel.csv
XML pouze pro medaile a detail kol + metadata turnaje.

Spusteni:
    python3 generate_presentation.py
"""

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aggregate_results import category_sort_key
from category_cske import KATA_INDIVIDUAL, KUMITE_INDIVIDUAL, KUMITE_WEIGHTS
from config import (
    AGGREGATED_XML,
    EXCEL_CSV,
    PRESENTATION_HTML,
    QUALIFYING_PLACES,
)
from nomination_io import format_category_name, xml_text
from qualification import is_ano_value
from utils import normalizuj


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def row_lookup_key(category: str, lastname: str, firstname: str) -> Tuple[str, str, str]:
    return (normalizuj(category), normalizuj(lastname), normalizuj(firstname))


def load_csv_rows(csv_path: Path) -> Tuple[List[str], List[dict]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader)
        rows = []
        for row in reader:
            if len(row) < len(header):
                row.extend([""] * (len(header) - len(row)))
            rows.append(dict(zip(header, row)))
    return header, rows


def build_xml_enrichment(xml_path: Path) -> Dict[Tuple[str, str, str], dict]:
    root = ET.parse(xml_path).getroot()
    enrichment: Dict[Tuple[str, str, str], dict] = {}

    for category in root.findall("category"):
        disciplina = xml_text(category, "disciplina")
        kategorie1 = xml_text(category, "kategorie1")
        kategorie2 = xml_text(category, "kategorie2")
        display = format_category_name(disciplina, kategorie1, kategorie2)

        for result in category.findall("result"):
            firstname = xml_text(result, "firstname")
            lastname = xml_text(result, "lastname")
            key = row_lookup_key(display, lastname, firstname)

            rounds_parts = []
            starts_elem = result.find("starts")
            if starts_elem is not None:
                for start in starts_elem.findall("start"):
                    round_date = xml_text(start, "round_date")
                    start_points = xml_text(start, "points")
                    start_position = xml_text(start, "position")
                    rounds_parts.append(f"{round_date}: {start_points}b ({start_position})")

            enrichment[key] = {
                "gold": xml_text(result, "gold_medals") or "0",
                "silver": xml_text(result, "silver_medals") or "0",
                "bronze": xml_text(result, "bronze_medals") or "0",
                "rounds": ", ".join(rounds_parts),
            }

    return enrichment


def category_sort_key_from_display(display_name: str) -> tuple:
    upper = display_name.upper()
    for label in (
        "KUMITE BEGINNER",
        "KATA BEGINNER",
        "KUMITE BALLOON",
        "KIHON IDO",
        "KARATE AGILITY",
    ):
        if upper.startswith(label):
            rest = display_name[len(label):].strip()
            return category_sort_key((label.title(), rest, ""))
    parts = display_name.split(None, 1)
    disciplina = parts[0] if parts else ""
    kategorie1 = parts[1] if len(parts) > 1 else ""
    return category_sort_key((disciplina, kategorie1, ""))


def discipline_from_category(category_name: str) -> str:
    upper = category_name.upper()
    for label in (
        "KUMITE BEGINNER",
        "KATA BEGINNER",
        "KUMITE BALLOON",
        "KIHON IDO",
        "KARATE AGILITY",
    ):
        if upper.startswith(label):
            return label
    return category_name.split()[0] if category_name else ""


# Barvy disciplín (border + nadpis + legenda). Bez fialove AI palety.
DISCIPLINE_COLORS: Dict[str, dict[str, str]] = {
    "KATA": {"accent": "#1565c0", "bg": "#e3f2fd", "label": "KATA"},
    "KUMITE": {"accent": "#c62828", "bg": "#ffebee", "label": "KUMITE"},
    "KATA BEGINNER": {"accent": "#0277bd", "bg": "#e1f5fe", "label": "KATA BEGINNER"},
    "KUMITE BEGINNER": {"accent": "#ad1457", "bg": "#fce4ec", "label": "KUMITE BEGINNER"},
    "KARATE AGILITY": {"accent": "#ef6c00", "bg": "#fff3e0", "label": "KARATE AGILITY"},
    "KIHON IDO": {"accent": "#558b2f", "bg": "#f1f8e9", "label": "KIHON IDO"},
    "KUMITE BALLOON": {"accent": "#00838f", "bg": "#e0f7fa", "label": "KUMITE BALLOON"},
}


def discipline_color(disciplina: str) -> dict[str, str]:
    """Vrati barvy discipliny; fallback pro nezname."""
    if disciplina in DISCIPLINE_COLORS:
        return DISCIPLINE_COLORS[disciplina]
    return {"accent": "#546e7a", "bg": "#eceff1", "label": disciplina}


def discipline_css_slug(disciplina: str) -> str:
    return normalizuj(disciplina).replace(" ", "-")


def _weights_for_kumite_age(age_label: str) -> Optional[tuple[str, ...]]:
    """Najde hmotnostni kategorie pro vekovy label z predpisu CSKe."""
    age_n = normalizuj(age_label)
    for weight_cat in KUMITE_WEIGHTS:
        parts = [part.strip() for part in weight_cat.age_label.split("/")]
        full_parts = [normalizuj(parts[0])]
        prefix = parts[0].rsplit(" ", 1)[0] if " " in parts[0] else parts[0]
        for part in parts[1:]:
            part = part.strip()
            if " " in part or normalizuj(part).startswith(normalizuj(prefix)):
                full_parts.append(normalizuj(part))
            else:
                full_parts.append(normalizuj(f"{prefix} {part}"))
        if age_n in full_parts:
            return weight_cat.weights
    return None


def build_official_display_categories() -> List[Tuple[str, str]]:
    """Oficialni kategorie CSKe jako (disciplina, display_name) pro HTML."""
    result: List[Tuple[str, str]] = []
    for cat in KATA_INDIVIDUAL:
        result.append(("KATA", format_category_name("kata", cat.label, "")))
    for cat in KUMITE_INDIVIDUAL:
        weights = _weights_for_kumite_age(cat.label)
        if not weights:
            result.append(("KUMITE", format_category_name("kumite", cat.label, "")))
            continue
        for weight in weights:
            result.append(("KUMITE", format_category_name("kumite", cat.label, weight)))
    return result


def official_category_keys(official: List[Tuple[str, str]]) -> set[str]:
    return {normalizuj(name) for _disc, name in official}


def rounds_from_csv_row(row: dict, round_columns: List[str]) -> str:
    parts = []
    for column in round_columns:
        value = row.get(column, "").strip()
        if value and value != "-":
            parts.append(f"{column}: {value}b")
    return ", ".join(parts)


def postup_class(value: str, prefix: str) -> str:
    suffix = "ano" if is_ano_value(value) else "ne"
    return f"{prefix}-{suffix}"


LEGEND_LINK_KRAJE = (
    '<a class="col-legend-link" href="#legenda-postupu" '
    'title="Vysvětlení sloupce postup z Kraje">postup z Kraje</a>'
)
LEGEND_LINK_POSTUPUJE = (
    '<a class="col-legend-link" href="#legenda-postupu" '
    'title="Vysvětlení sloupce Postupuje">Postupuje</a>'
)
TABLE_HEAD_POSTUP = (
    f"<th>{LEGEND_LINK_KRAJE}</th><th>{LEGEND_LINK_POSTUPUJE}</th>"
    f'<th class="copy-nomination-col" title="Kopirovat radek pro nominations/*.txt">Txt</th>'
)

COPY_NOMINATION_CELL = (
    '<td class="copy-nomination-cell">'
    '<button type="button" class="copy-nomination-btn" '
    'title="Kopirovat radek pro nominations/ nebo nominations-declined/" '
    'aria-label="Kopirovat radek nominace">Kopie</button>'
    "</td>"
)

COPY_NOMINATION_SCRIPT = """
(function () {
  function nominationLine(row) {
    const first = row.dataset.firstname || "";
    const last = row.dataset.lastname || "";
    const category = row.dataset.category || "";
    return first + " " + last + " - " + category;
  }

  async function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest(".copy-nomination-btn");
    if (!button) return;
    const row = button.closest("tr[data-firstname]");
    if (!row) return;
    const text = nominationLine(row);
    try {
      await copyText(text);
      button.classList.add("copy-nomination-ok");
      const oldTitle = button.title;
      button.title = "Zkopirovano";
      setTimeout(() => {
        button.classList.remove("copy-nomination-ok");
        button.title = oldTitle;
      }, 1500);
    } catch {
      window.prompt("Kopirovani se nezdarilo, zkopiruj rucne:", text);
    }
  });
})();
"""


FILTER_SCRIPT = """
(function () {
  const storageKey = "nominace-mcr-filters";
  const filterData = window.PRESENTATION_FILTER_DATA;
  const clubSelect = document.getElementById("filter-club");
  const mainSelect = document.getElementById("filter-main");
  const detailSelect = document.getElementById("filter-detail");
  const resetButton = document.getElementById("filter-reset");
  const onlyClubCheckbox = document.getElementById("filter-only-club");
  const onlyPostupCheckbox = document.getElementById("filter-only-postup");
  const onlyRemizaCheckbox = document.getElementById("filter-only-remiza");
  const showUnofficialCheckbox = document.getElementById("filter-show-unofficial");
  const showEmptyCheckbox = document.getElementById("filter-show-empty");
  const statusEl = document.getElementById("filter-status");

  function saveFilters() {
    localStorage.setItem(storageKey, JSON.stringify({
      club: clubSelect.value,
      main: mainSelect.value,
      detail: detailSelect.value,
      onlyClub: onlyClubCheckbox.checked,
      onlyPostup: onlyPostupCheckbox.checked,
      onlyRemiza: onlyRemizaCheckbox.checked,
      showUnofficial: showUnofficialCheckbox.checked,
      showEmpty: showEmptyCheckbox.checked,
    }));
  }

  function loadFilters() {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "{}");
    } catch {
      return {};
    }
  }

  function populateDetailOptions() {
    const main = mainSelect.value;
    const previous = detailSelect.value;
    detailSelect.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "Vše";
    detailSelect.appendChild(allOption);

    const categories = main
      ? (filterData.categoriesByDiscipline[main] || [])
      : filterData.allCategories;

    for (const category of categories) {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category.replace(/^[^ ]+ /, "");
      detailSelect.appendChild(option);
    }

    if (categories.includes(previous)) {
      detailSelect.value = previous;
    } else {
      detailSelect.value = "";
    }
  }

  function categoryHasClub(section, club) {
    if (!club) return true;
    const clubs = JSON.parse(section.dataset.clubs || "[]");
    return clubs.includes(club);
  }

  function isPostupRow(row) {
    const postupujeValue = row.dataset.postupuje || "";
    return postupujeValue.startsWith("ANO");
  }

  function isRemizaRow(row) {
    const postupujeValue = row.dataset.postupuje || "";
    const krajeValue = row.dataset.postupKraje || "";
    return postupujeValue.includes("remiza") || krajeValue.includes("remiza");
  }

  function updateOnlyClubState() {
    const hasClub = Boolean(clubSelect.value);
    onlyClubCheckbox.disabled = !hasClub;
    if (!hasClub) onlyClubCheckbox.checked = false;
  }

  function applyFilters() {
    const club = clubSelect.value;
    const main = mainSelect.value;
    const detail = detailSelect.value;
    const onlyClub = onlyClubCheckbox.checked && club;
    const onlyPostup = onlyPostupCheckbox.checked;
    const onlyRemiza = onlyRemizaCheckbox.checked;
    const showEmpty = showEmptyCheckbox.checked;
    const showUnofficial = showUnofficialCheckbox.checked;
    let visibleCategories = 0;
    let visibleRows = 0;
    let highlightedRows = 0;
    let visibleEmpty = 0;
    let visibleUnofficial = 0;

    document.querySelectorAll(".category").forEach((section) => {
      const isEmpty = section.dataset.empty === "1";
      const isOfficial = section.dataset.official === "1";
      const matchMain = !main || section.dataset.discipline === main;
      const matchDetail = !detail || section.dataset.category === detail;
      const matchClub = isEmpty ? !club : categoryHasClub(section, club);
      let categoryVisible = matchMain && matchDetail && matchClub;
      // Checkbox: zobrazit / skryt mimo predpis (Open, U8, ...)
      if (!isOfficial && !showUnofficial) {
        categoryVisible = false;
      }
      if (isEmpty && (!showEmpty || onlyPostup || onlyRemiza || onlyClub)) {
        categoryVisible = false;
      }
      let categoryRows = 0;

      section.querySelectorAll("tbody tr").forEach((row) => {
        let rowVisible = true;
        if (onlyClub && row.dataset.club !== club) rowVisible = false;
        if (onlyPostup && !isPostupRow(row)) rowVisible = false;
        if (onlyRemiza && !isRemizaRow(row)) rowVisible = false;
        row.hidden = !rowVisible;
        row.classList.toggle("club-highlight", Boolean(club && row.dataset.club === club));
        if (rowVisible) {
          categoryRows += 1;
          visibleRows += 1;
          if (club && row.dataset.club === club) highlightedRows += 1;
        }
      });

      if (categoryVisible && categoryRows === 0 && !isEmpty) categoryVisible = false;
      section.hidden = !categoryVisible;

      if (categoryVisible) {
        visibleCategories += 1;
        if (isEmpty) visibleEmpty += 1;
        if (!isOfficial) visibleUnofficial += 1;
      }
    });

    document.querySelectorAll(".discipline").forEach((section) => {
      const hasVisible = Array.from(section.querySelectorAll(".category"))
        .some((category) => !category.hidden);
      section.hidden = !hasVisible;
    });

    let postupuje = 0;
    let remiza = 0;
    let cekatele = 0;

    document.querySelectorAll(".category:not([hidden]) tbody tr:not([hidden])").forEach((row) => {
      if (onlyClub && row.dataset.club !== club) return;

      const postupujeValue = row.dataset.postupuje || "";
      const krajeValue = row.dataset.postupKraje || "";

      if (postupujeValue.startsWith("ANO")) postupuje += 1;
      if (postupujeValue.includes("remiza") || krajeValue.includes("remiza")) remiza += 1;
      if (postupujeValue === "NE (zájem o postup)") cekatele += 1;
    });

    const parts = [visibleCategories + " kategorií", visibleRows + " řádků"];
    if (visibleEmpty) parts.push(visibleEmpty + " prázdných");
    if (visibleUnofficial) parts.push(visibleUnofficial + " mimo offic. kategorie");
    if (club) parts.push(highlightedRows + " z vybraného klubu");
    if (onlyClub) parts.push("jen vybraný klub");
    if (onlyPostup) parts.push("jen postupy");
    if (onlyRemiza) parts.push("jen remízy");
    if (!showUnofficial) parts.push("bez mimo offic. kategorie");
    parts.push("Postupuje: " + postupuje);
    parts.push("Remízy: " + remiza);
    parts.push("Čekatelé: " + cekatele);
    statusEl.textContent = "Zobrazeno: " + parts.join(" · ");
    saveFilters();
  }

  window.applyPresentationFilters = applyFilters;
  window.resetPresentationFilters = resetFilters;

  function resetFilters() {
    clubSelect.value = "";
    mainSelect.value = "";
    detailSelect.value = "";
    onlyClubCheckbox.checked = false;
    onlyPostupCheckbox.checked = false;
    onlyRemizaCheckbox.checked = false;
    showUnofficialCheckbox.checked = true;
    showEmptyCheckbox.checked = true;
    updateOnlyClubState();
    populateDetailOptions();
    applyFilters();
  }

  filterData.clubs.forEach((club) => {
    const option = document.createElement("option");
    option.value = club;
    option.textContent = club;
    clubSelect.appendChild(option);
  });

  function applyDisciplineSelectColor() {
    const value = mainSelect.value;
    const colors = (filterData.disciplineColors || {})[value];
    if (colors) {
      mainSelect.style.color = colors.accent;
      mainSelect.style.borderColor = colors.accent;
      mainSelect.style.background = colors.bg;
      mainSelect.style.fontWeight = "600";
    } else {
      mainSelect.style.color = "";
      mainSelect.style.borderColor = "";
      mainSelect.style.background = "";
      mainSelect.style.fontWeight = "";
    }
  }

  filterData.disciplines.forEach((discipline) => {
    const option = document.createElement("option");
    option.value = discipline;
    option.textContent = discipline;
    const colors = (filterData.disciplineColors || {})[discipline];
    if (colors) {
      option.style.color = colors.accent;
      option.style.fontWeight = "600";
      option.dataset.disciplineSlug = discipline.toLowerCase().replace(/\\s+/g, "-");
    }
    mainSelect.appendChild(option);
  });
  applyDisciplineSelectColor();

  const saved = loadFilters();
  if (saved.club && filterData.clubs.includes(saved.club)) clubSelect.value = saved.club;
  if (saved.main && filterData.disciplines.includes(saved.main)) mainSelect.value = saved.main;
  populateDetailOptions();
  if (saved.detail && filterData.allCategories.includes(saved.detail)) {
    detailSelect.value = saved.detail;
  }
  if (saved.onlyClub) onlyClubCheckbox.checked = true;
  if (saved.onlyPostup) onlyPostupCheckbox.checked = true;
  if (saved.onlyRemiza) onlyRemizaCheckbox.checked = true;
  showUnofficialCheckbox.checked = saved.showUnofficial !== false;
  showEmptyCheckbox.checked = saved.showEmpty !== false;
  applyDisciplineSelectColor();
  updateOnlyClubState();

  clubSelect.addEventListener("change", () => {
    updateOnlyClubState();
    applyFilters();
  });
  mainSelect.addEventListener("change", () => {
    detailSelect.value = "";
    populateDetailOptions();
    applyDisciplineSelectColor();
    applyFilters();
  });
  detailSelect.addEventListener("change", applyFilters);
  onlyClubCheckbox.addEventListener("change", applyFilters);
  onlyPostupCheckbox.addEventListener("change", applyFilters);
  onlyRemizaCheckbox.addEventListener("change", applyFilters);
  showUnofficialCheckbox.addEventListener("change", applyFilters);
  showEmptyCheckbox.addEventListener("change", applyFilters);
  resetButton.addEventListener("click", resetFilters);

  applyFilters();
  if (typeof window.updateNominationMenus === "function") {
    window.updateNominationMenus();
  }
})();
"""


def build_discipline_swatches_html(disciplines: List[str]) -> str:
    """Barevne swatche disciplín."""
    return "".join(
        (
            f'<span class="swatch swatch-discipline" '
            f'style="background:{escape_html(discipline_color(disc)["bg"])};'
            f'border-left-color:{escape_html(discipline_color(disc)["accent"])};'
            f'color:{escape_html(discipline_color(disc)["accent"])}">'
            f'{escape_html(disc)}</span>'
        )
        for disc in disciplines
    )


def build_color_key_html(disciplines: List[str]) -> str:
    """Legenda barev pod filtry - stitky jsou zaroven klikaci filtry."""
    discipline_buttons = "".join(
        (
            f'<button type="button" class="swatch swatch-discipline swatch-filter" '
            f'data-key-discipline="{escape_html(disc)}" aria-pressed="false" '
            f'title="Zobrazit jen {escape_html(disc)} (znovu kliknout = vše)" '
            f'style="background:{escape_html(discipline_color(disc)["bg"])};'
            f'border-left-color:{escape_html(discipline_color(disc)["accent"])};'
            f'color:{escape_html(discipline_color(disc)["accent"])}">'
            f'{escape_html(disc)}</button>'
        )
        for disc in disciplines
    )
    return (
        f'<section class="color-key" aria-label="Legenda barev a rychlé filtry">'
        f'<div class="color-key-block">'
        f'<p class="legend-subtitle">Disciplíny</p>'
        f'<div class="legend-swatches">{discipline_buttons}</div>'
        f"</div>"
        f'<div class="color-key-block">'
        f'<p class="legend-subtitle">Označení kategorií</p>'
        f'<div class="legend-swatches">'
        f'<button type="button" class="swatch swatch-unofficial swatch-filter" '
        f'data-key-toggle="filter-show-unofficial" aria-pressed="true" '
        f'title="Zobrazit / skrýt kategorie mimo předpis">mimo offic. kategorie</button>'
        f'<button type="button" class="swatch swatch-empty swatch-filter" '
        f'data-key-toggle="filter-show-empty" aria-pressed="true" '
        f'title="Zobrazit / skrýt prázdné oficiální kategorie">prázdná oficiální</button>'
        f"</div>"
        f"</div>"
        f"</section>"
    )


COLOR_KEY_SCRIPT = """
(function () {
  var mainSelect = document.getElementById("filter-main");
  var resetButton = document.getElementById("filter-reset");
  var disciplineButtons = document.querySelectorAll(".color-key [data-key-discipline]");
  var toggleButtons = document.querySelectorAll(".color-key [data-key-toggle]");
  if (!mainSelect) return;

  function sync() {
    disciplineButtons.forEach(function (btn) {
      var active = mainSelect.value === btn.dataset.keyDiscipline;
      btn.classList.toggle("swatch-active", active);
      btn.classList.toggle("swatch-dim", !!mainSelect.value && !active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    toggleButtons.forEach(function (btn) {
      var box = document.getElementById(btn.dataset.keyToggle);
      var on = box ? box.checked : true;
      btn.classList.toggle("swatch-off", !on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  disciplineButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var disc = btn.dataset.keyDiscipline;
      mainSelect.value = mainSelect.value === disc ? "" : disc;
      mainSelect.dispatchEvent(new Event("change"));
    });
  });
  toggleButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var box = document.getElementById(btn.dataset.keyToggle);
      if (!box) return;
      box.checked = !box.checked;
      box.dispatchEvent(new Event("change"));
    });
  });

  mainSelect.addEventListener("change", sync);
  toggleButtons.forEach(function (btn) {
    var box = document.getElementById(btn.dataset.keyToggle);
    if (box) box.addEventListener("change", sync);
  });
  if (resetButton) resetButton.addEventListener("click", function () { setTimeout(sync, 0); });
  sync();
})();
"""


FINAL_TAB_HASH = "finalni-postupujici"

TABS_SCRIPT = """
(function () {
  var tabs = document.querySelectorAll(".tab-btn");
  var panels = {
    results: document.getElementById("main-content"),
    final: document.getElementById("final-tab")
  };
  function show(name) {
    Object.keys(panels).forEach(function (key) {
      if (panels[key]) panels[key].hidden = key !== name;
    });
    tabs.forEach(function (btn) {
      var active = btn.dataset.tab === name;
      btn.classList.toggle("tab-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }
  tabs.forEach(function (btn) {
    btn.addEventListener("click", function () {
      show(btn.dataset.tab);
      try {
        var url = btn.dataset.tab === "final"
          ? "#" + FINAL_HASH
          : location.pathname + location.search;
        history.replaceState(null, "", url);
      } catch (e) { /* napr. otevreno ze souboru - zalozka funguje i bez URL */ }
    });
  });
  show(location.hash === "#" + FINAL_HASH ? "final" : "results");

  var clubSelect = document.getElementById("final-club");
  var summary = document.getElementById("final-summary");
  function applyFinalFilter() {
    var club = clubSelect ? clubSelect.value : "";
    var people = 0, cats = 0;
    document.querySelectorAll("#final-tab .final-category").forEach(function (section) {
      var visible = 0;
      section.querySelectorAll("tbody tr").forEach(function (row) {
        var show = !club || row.dataset.club === club;
        row.hidden = !show;
        if (show) visible += 1;
      });
      section.hidden = visible === 0;
      var count = section.querySelector(".final-count");
      if (count) count.textContent = "(" + visible + ")";
      if (visible) { cats += 1; people += visible; }
    });
    document.querySelectorAll("#final-tab .final-discipline").forEach(function (group) {
      var n = 0;
      group.querySelectorAll("tbody tr").forEach(function (row) { if (!row.hidden) n += 1; });
      group.hidden = n === 0;
      var label = group.querySelector(".final-discipline-count");
      if (label) label.textContent = n + (n === 1 ? " postupující" : " postupujících");
    });
    if (summary) {
      summary.textContent = "Celkem postupujících: " + people + " | Kategorií: " + cats +
        (club ? " | Klub: " + club : "");
    }
  }
  if (clubSelect) clubSelect.addEventListener("change", applyFinalFilter);
  applyFinalFilter();
})();
""".replace("FINAL_HASH", '"' + FINAL_TAB_HASH + '"')


def build_manual_edits_html(items: List[dict]) -> str:
    """Prehled rucnich uprav (rucni-upravy.txt) pod finalnim seznamem."""
    if not items:
        return ""
    cards = []
    for item in items:
        if item["akce"] in ("PRESUN", "PRESTUP"):
            change = (
                f'<span class="me-cat me-cat-old">{escape_html(item["z"])}</span>'
                '<span class="me-arrow" aria-hidden="true">→</span>'
                f'<span class="me-cat">{escape_html(item["do"])}</span>'
            )
        elif item["akce"] == "PRIDAT":
            change = (
                '<span class="me-arrow" aria-hidden="true">+</span>'
                f'<span class="me-cat">{escape_html(item["do"])}</span>'
            )
        else:
            change = f'<span class="me-cat me-cat-old">{escape_html(item["z"])}</span>'
        reason = (
            f'<p class="me-reason">{escape_html(item["duvod"])}</p>' if item["duvod"] else ""
        )
        date = f'<span class="me-date">{escape_html(item["datum"])}</span>' if item["datum"] else ""
        cards.append(
            f'<li class="me-card me-{item["akce"].lower()}">'
            '<div class="me-top">'
            f'<span class="me-type">{escape_html(item["typ"])}</span>{date}'
            "</div>"
            f'<p class="me-name">{escape_html(item["zavodnik"])}'
            f'<span class="me-club">{escape_html(item["klub"])}</span></p>'
            f'<p class="me-change">{change}</p>'
            f"{reason}"
            "</li>"
        )
    return (
        '<section class="manual-edits" id="rucni-upravy">'
        "<h2>Ruční úpravy seznamu</h2>"
        '<p class="final-intro">Změny oproti výsledkům, provedené ručně (žádosti klubů, přestupy). '
        "V seznamu výše jsou označené štítkem <span class=\"final-badge\">ruční úprava</span> "
        "nebo <span class=\"final-badge\">přestup</span>.</p>"
        f'<ul class="me-list">{"".join(cards)}</ul>'
        "</section>"
    )


def build_final_tab_html(final_rows: List[dict], manual_items: List[dict] | None = None) -> str:
    """Zalozka s konecnym seznamem postupujicich (stejna data jako final-postupujici.pdf)."""
    by_category: OrderedDict[str, List[dict]] = OrderedDict()
    for row in final_rows:
        by_category.setdefault(row["Kategorie"], []).append(row)
    clubs = sorted({row["Klub"] for row in final_rows})

    badge_titles = {
        "presun": "Ručně přesunuto z jiné kategorie",
        "pridat": "Ručně doplněno mimo pořadí",
        "prestup": "Přestup po skončení kol",
    }
    sections_by_disc: OrderedDict[str, List[str]] = OrderedDict()
    for category, rows in by_category.items():
        body = []
        for row in rows:
            uprava = row.get("Uprava", "")
            title = badge_titles.get(uprava, "")
            if uprava == "prestup" and row.get("Prestup_z"):
                title += f", dříve {row['Prestup_z']}"
            badge = (
                f' <span class="final-badge" title="{escape_html(title)}">'
                f'{"přestup" if uprava == "prestup" else "ruční úprava"}</span>'
                if uprava in badge_titles else ""
            )
            body.append(
                f'<tr data-club="{escape_html(row["Klub"])}">'
                f'<td>{escape_html(row["Jmeno"])} {escape_html(row["Prijmeni"])}{badge}</td>'
                f'<td>{escape_html(row["Klub"])}</td></tr>'
            )
        disciplina = discipline_from_category(category)
        sections_by_disc.setdefault(disciplina, []).append(
            f'<section class="final-category" data-discipline="{escape_html(disciplina)}">'
            f'<h3>{escape_html(category)} <span class="final-count">({len(rows)})</span></h3>'
            '<table><colgroup><col class="final-col-name"><col></colgroup>'
            "<thead><tr><th>Závodník</th><th>Klub</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></section>"
        )

    # KATA a KUMITE zvlast, ve stejnych barvach jako na zalozce Vysledky
    groups = []
    for disciplina, blocks in sections_by_disc.items():
        colors = discipline_color(disciplina)
        groups.append(
            f'<section class="final-discipline" data-discipline="{escape_html(disciplina)}" '
            f'style="--disc-accent:{escape_html(colors["accent"])};--disc-bg:{escape_html(colors["bg"])}">'
            f'<h2 class="final-discipline-title">{escape_html(disciplina)}'
            f' <span class="final-discipline-count"></span></h2>'
            f'<div class="final-list">{"".join(blocks)}</div>'
            "</section>"
        )

    club_options = "".join(
        f'<option value="{escape_html(club)}">{escape_html(club)}</option>' for club in clubs
    )
    return (
        '<div id="final-tab" hidden>'
        '<section class="final-head">'
        "<h2>Finální postupující na nominační turnaj</h2>"
        '<p class="final-intro">Konečný seznam po nominacích klubů a ručních úpravách. '
        "Jen oficiální kategorie ČSKe, seřazeno KATA → KUMITE podle věku. "
        "Stejná data jako PDF exportu.</p>"
        '<div class="final-controls">'
        '<div class="filter-field"><label for="final-club">Klub</label>'
        f'<select id="final-club"><option value="">Vše</option>{club_options}</select></div>'
        f'<p class="final-summary" id="final-summary">Celkem postupujících: {len(final_rows)}'
        f" | Kategorií: {len(by_category)}</p>"
        "</div></section>"
        f'{"".join(groups)}'
        f"{build_manual_edits_html(manual_items or [])}"
        "</div>"
    )


def build_legend_html(qualifying_places: int) -> str:
    """Dolni legenda postupu (bez barevnych swatchu)."""
    limit = qualifying_places
    items = [
        (
            "postup z Kraje: ANO",
            f"Závodník je v prvních {limit} místech kategorie podle součtu bodů z kol.",
        ),
        (
            "Postupuje: ANO",
            "Postup z pořadí nebo doplnění slotu po odmítnutí. "
            f"V kategorii je vždy {limit} postupujících (kromě remízy na hraně).",
        ),
        (
            "Postupuje: ANO (potvrzeno)",
            "Postupuje a klub potvrdil nominaci (soubor v nominations/).",
        ),
        (
            "Postupuje: ANO (remíza)",
            "Aktivní remíza na hraně postupu "
            f"({limit}. místo): soupeři na stejné tabulce pozici by překročili limit "
            f"{limit} postupujících.",
        ),
        (
            "Postupuje: NE (zájem o postup)",
            "Nepostupuje, ale klub projevil zájem (nominations/) – "
            "informace pro ostatní trenéry, slot se plní dle pořadí.",
        ),
        (
            "Postupuje: NE (odmítnuto)",
            "Klub nominaci odmítl (nominations-declined/). "
            "Slot přebírá další v pořadí.",
        ),
        (
            "Postupuje: NE",
            "Nepostupuje (mimo postup z pořadí a bez volného slotu).",
        ),
        (
            "mimo offic. kategorie",
            "Oranžové zvýraznění — kategorie je ve výsledcích, "
            "ale není v oficiálním seznamu ČSKe (např. KATA U8).",
        ),
        (
            "Prázdná kategorie",
            "Oficiální kategorie ČSKe bez závodníků — zobrazena na konci "
            "příslušné disciplíny (šedý rámeček).",
        ),
    ]
    rows = "".join(
        f"<dt>{escape_html(label)}</dt><dd>{escape_html(text)}</dd>"
        for label, text in items
    )
    return (
        f"<section id=\"legenda-postupu\" class=\"legend\">"
        f"<h2>Legenda</h2>"
        f"<p class=\"legend-intro\">Limit postupujících v kategorii: "
        f"<strong>{limit}</strong>.</p>"
        f"<p class=\"legend-subtitle\">Postupy</p>"
        f"<dl>{rows}</dl>"
        f"</section>"
    )


def build_discipline_color_css(disciplines: List[str]) -> str:
    """CSS pravidla pro barevne odliseni disciplín."""
    parts: list[str] = []
    for disc in disciplines:
        colors = discipline_color(disc)
        slug = discipline_css_slug(disc)
        accent = colors["accent"]
        bg = colors["bg"]
        parts.append(
            f".discipline[data-discipline=\"{disc}\"] {{"
            f" border-left: 6px solid {accent};"
            f" background: linear-gradient(90deg, {bg} 0%, #ffffff 48px);"
            f" }}"
            f".discipline[data-discipline=\"{disc}\"] > h2 {{"
            f" color: {accent};"
            f" }}"
            f".discipline[data-discipline=\"{disc}\"] > h2::before {{"
            f" content: \"\";"
            f" display: inline-block;"
            f" width: 10px; height: 10px; border-radius: 2px;"
            f" background: {accent}; margin-right: 8px; vertical-align: middle;"
            f" }}"
            f"option[data-discipline-slug=\"{slug}\"] {{"
            f" color: {accent}; font-weight: 600;"
            f" }}"
        )
    return "".join(parts)


def generate_html(
    xml_path: Path,
    csv_path: Path,
    output_path: Path,
) -> None:
    root = ET.parse(xml_path).getroot()
    _, csv_rows = load_csv_rows(csv_path)
    enrichment = build_xml_enrichment(xml_path)

    # Prestupy z rucni-upravy.txt (PRESTUP) - stitek u klubu ve vysledcich
    from manual_edits import load_transfers

    transfers = {normalizuj(t["zavodnik"]): t for t in load_transfers()}

    def transfer_badge(firstname: str, lastname: str, club: str) -> str:
        transfer = transfers.get(normalizuj(f"{firstname} {lastname}"))
        if not transfer or normalizuj(club) != normalizuj(transfer["do"]):
            return ""
        tip = f"Ruční úprava: přestup, dříve {transfer['z']}"
        if transfer["duvod"]:
            tip += f" – {transfer['duvod']}"
        if transfer["datum"]:
            tip += f" ({transfer['datum']})"
        return (
            f' <span class="transfer-badge" title="{escape_html(tip)}">'
            f'přestup <span class="transfer-from">z {escape_html(transfer["z"])}</span></span>'
        )

    tournament_name = xml_text(root, "name")
    tournament_date = xml_text(root, "date")
    competitors = xml_text(root, "number_of_competitors")
    starts = xml_text(root, "number_of_starts")
    clubs = xml_text(root, "number_of_clubs")
    rounds = xml_text(root, "number_of_rounds")

    if not csv_rows:
        output_path.write_text("<html><body>CSV je prazdne.</body></html>", encoding="utf-8")
        return

    sample = csv_rows[0]
    round_columns = [
        key for key in sample
        if key not in {
            "Pořadí", "Kategorie", "Jméno", "Příjmení", "celé Jméno", "Klub",
            "Celkem", "postup z Kraje", "Postupuje", "Poznamka postupu",
        }
    ]

    by_category: OrderedDict[str, List[dict]] = OrderedDict()
    for row in csv_rows:
        category = row.get("Kategorie", "")
        by_category.setdefault(category, []).append(row)

    official_list = build_official_display_categories()
    official_keys = official_category_keys(official_list)

    filled_all = sorted(by_category.keys(), key=category_sort_key_from_display)
    filled_official = [name for name in filled_all if normalizuj(name) in official_keys]
    filled_unofficial = [name for name in filled_all if normalizuj(name) not in official_keys]
    # Open / mimo predpis vzdy na konci (po prazdnych oficialnich)
    empty_official = [
        (disc, name)
        for disc, name in official_list
        if normalizuj(name) not in {normalizuj(c) for c in filled_all}
    ]
    empty_official.sort(key=lambda item: category_sort_key_from_display(item[1]))

    all_clubs = sorted({
        row.get("Klub", "").strip()
        for row in csv_rows
        if row.get("Klub", "").strip()
    })
    categories_by_discipline: dict[str, list[str]] = defaultdict(list)
    for category_name in filled_official:
        categories_by_discipline[discipline_from_category(category_name)].append(category_name)
    for disc, name in empty_official:
        if name not in categories_by_discipline[disc]:
            categories_by_discipline[disc].append(name)
    for category_name in filled_unofficial:
        categories_by_discipline[discipline_from_category(category_name)].append(category_name)

    preferred_discipline_order = [
        "KARATE AGILITY",
        "KIHON IDO",
        "KUMITE BALLOON",
        "KATA BEGINNER",
        "KUMITE BEGINNER",
        "KATA",
        "KUMITE",
    ]
    present_disciplines = set(categories_by_discipline.keys())
    discipline_order = [d for d in preferred_discipline_order if d in present_disciplines]
    discipline_order.extend(sorted(present_disciplines - set(discipline_order)))

    all_categories_for_filter = (
        filled_official
        + [name for _disc, name in empty_official]
        + filled_unofficial
    )
    filter_data = {
        "clubs": all_clubs,
        "disciplines": discipline_order,
        "disciplineColors": {
            d: discipline_color(d) for d in discipline_order
        },
        "categoriesByDiscipline": {
            d: categories_by_discipline[d] for d in discipline_order
        },
        "allCategories": all_categories_for_filter,
    }
    filter_json = json.dumps(filter_data, ensure_ascii=False).replace("<", "\\u003c")
    color_key_html = build_color_key_html(discipline_order)
    legend_html = build_legend_html(QUALIFYING_PLACES)
    discipline_color_css = build_discipline_color_css(discipline_order)

    def render_filled_category(category_name: str) -> str:
        category_rows = by_category[category_name]
        category_note = category_rows[0].get("Poznamka postupu", "").strip()
        rows_html = []
        clubs_in_category = sorted({
            row.get("Klub", "").strip()
            for row in category_rows
            if row.get("Klub", "").strip()
        })
        disciplina = discipline_from_category(category_name)
        is_official = normalizuj(category_name) in official_keys
        is_open = "open" in normalizuj(category_name)
        for row in category_rows:
            firstname = row.get("Jméno", "")
            lastname = row.get("Příjmení", "")
            club = row.get("Klub", "")
            key = row_lookup_key(category_name, lastname, firstname)
            extra = enrichment.get(key, {})

            postupuje = row.get("Postupuje", "NE")
            postup_z_kraje = row.get("postup z Kraje", "NE")

            gold = extra.get("gold", "0")
            silver = extra.get("silver", "0")
            bronze = extra.get("bronze", "0")
            medals = []
            if int(gold) > 0:
                medals.append(f"<span class='medal gold'>{gold}</span>")
            if int(silver) > 0:
                medals.append(f"<span class='medal silver'>{silver}</span>")
            if int(bronze) > 0:
                medals.append(f"<span class='medal bronze'>{bronze}</span>")

            rounds_text = extra.get("rounds") or rounds_from_csv_row(row, round_columns)

            rows_html.append(
                f"<tr data-club=\"{escape_html(club)}\""
                f" data-firstname=\"{escape_html(firstname)}\""
                f" data-lastname=\"{escape_html(lastname)}\""
                f" data-category=\"{escape_html(category_name)}\""
                f" data-postupuje=\"{escape_html(postupuje)}\""
                f" data-postup-kraje=\"{escape_html(postup_z_kraje)}\">"
                f"<td>{escape_html(row.get('Pořadí', ''))}</td>"
                f"<td><strong>{escape_html(firstname)} {escape_html(lastname)}</strong></td>"
                f"<td>{escape_html(club)}{transfer_badge(firstname, lastname, club)}</td>"
                f"<td>{escape_html(row.get('Celkem', ''))}</td>"
                f"<td>{''.join(medals)}</td>"
                f"<td>{escape_html(rounds_text)}</td>"
                f"<td class='postup-z-kraje-cell {postup_class(postup_z_kraje, 'postup-z-kraje')}'>"
                f"{escape_html(postup_z_kraje)}</td>"
                f"<td class='postupuje-cell {postup_class(postupuje, 'postupuje')}'>"
                f"{escape_html(postupuje)}</td>"
                f"{COPY_NOMINATION_CELL}"
                "</tr>"
            )

        note_html = (
            f"<p class='category-note'>{escape_html(category_note)}</p>"
            if category_note
            else ""
        )
        clubs_json = json.dumps(clubs_in_category, ensure_ascii=False)
        classes = ["category"]
        if not is_official:
            classes.append("category-unofficial")
        if is_open:
            classes.append("category-open")
        return (
            f"<section class=\"{' '.join(classes)}\""
            f" data-discipline=\"{escape_html(disciplina)}\""
            f" data-category=\"{escape_html(category_name)}\""
            f" data-official=\"{'1' if is_official else '0'}\""
            f" data-open=\"{'1' if is_open else '0'}\""
            f" data-empty=\"0\""
            f" data-clubs=\"{escape_html(clubs_json)}\">"
            f"<h3>{escape_html(category_name)}</h3>"
            f"{note_html}"
            "<table>"
            "<thead><tr>"
            "<th>Poz.</th><th>Jmeno</th><th>Klub</th><th>Body</th><th>Medaile</th>"
            "<th>Kola</th>"
            f"{TABLE_HEAD_POSTUP}"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></section>"
        )

    def render_empty_category(disciplina: str, category_name: str) -> str:
        return (
            f"<section class=\"category category-empty\""
            f" data-discipline=\"{escape_html(disciplina)}\""
            f" data-category=\"{escape_html(category_name)}\""
            f" data-official=\"1\""
            f" data-open=\"0\""
            f" data-empty=\"1\""
            f" data-clubs=\"[]\">"
            f"<h3>{escape_html(category_name)}</h3>"
            f"<p class=\"category-empty-msg\">Žádní závodníci LSKe v této kategorii.</p>"
            f"</section>"
        )

    disciplines: dict[str, list[str]] = defaultdict(list)
    # 1) oficialni s vysledky, 2) prazdne oficialni, 3) Open / mimo predpis na konci
    for category_name in filled_official:
        disciplines[discipline_from_category(category_name)].append(
            render_filled_category(category_name)
        )
    for disc, name in empty_official:
        disciplines[disc].append(render_empty_category(disc, name))
    for category_name in filled_unofficial:
        disciplines[discipline_from_category(category_name)].append(
            render_filled_category(category_name)
        )

    discipline_html = []
    for disciplina in discipline_order:
        blocks = disciplines.get(disciplina)
        if not blocks:
            continue
        discipline_html.append(
            "<section class='discipline'"
            f" data-discipline=\"{escape_html(disciplina)}\">"
            f"<h2>{escape_html(disciplina)}</h2>"
            f"{''.join(blocks)}"
            "</section>"
        )

    login_html = ""
    content_open = '<div id="main-content">'
    tail_scripts = (
        f"  <script>window.PRESENTATION_FILTER_DATA = {filter_json};</script>\n"
        f"  <script>{FILTER_SCRIPT}</script>\n"
        f"  <script>{COPY_NOMINATION_SCRIPT}</script>\n"
        f"  <script>{TABS_SCRIPT}</script>\n"
        f"  <script>{COLOR_KEY_SCRIPT}</script>"
    )

    # Finalni postupujici - stejny vypocet jako final-postupujici.* (lazy import:
    # final_list importuje z tohoto modulu)
    from final_list import compute_final_list, describe_manual_edits

    final_rows, final_errors = compute_final_list(csv_path)
    if final_errors:
        raise SystemExit(
            "Chyba v rucnich upravach - web NEvygenerovan:\n  " + "\n  ".join(final_errors)
        )
    final_tab_html = build_final_tab_html(final_rows, describe_manual_edits(csv_path))

    html = f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape_html(tournament_name)}</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 0; background: #eef2ff; color: #222; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    header {{ background: #3949ab; color: white; padding: 24px; border-radius: 12px; margin-bottom: 24px; }}
    header h1 {{ margin: 0 0 12px; }}
    .stats {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: start; }}
    .stats span {{ background: rgba(255,255,255,0.15); padding: 6px 12px; border-radius: 8px; }}
    a.col-legend-link {{
      color: #3949ab; text-decoration: none; font-weight: 600;
    }}
    a.col-legend-link:hover {{ text-decoration: underline; }}
    .discipline {{ background: white; border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .discipline > h2 {{ margin: 0 0 4px; font-size: 22px; }}
    {discipline_color_css}
    .category {{ margin-top: 16px; }}
    .category-note {{ margin: 4px 0 12px; padding: 8px 12px; background: #fff8e1; border-left: 4px solid #f9a825; font-size: 14px; }}
    .category-unofficial {{
      background: #fff3e0; border-left: 4px solid #ef6c00; padding: 12px 12px 12px 16px; border-radius: 8px;
    }}
    .category-unofficial h3 {{ color: #e65100; }}
    .category-unofficial h3::after {{
      content: " (mimo offic. kategorie)"; font-size: 12px; font-weight: 600; color: #ef6c00; margin-left: 6px;
    }}
    .category-empty {{
      background: #fafafa; border: 1px dashed #bdbdbd; padding: 10px 14px; border-radius: 8px; opacity: 0.9;
    }}
    .category-empty h3 {{ color: #616161; font-weight: 600; }}
    .category-empty-msg {{ margin: 6px 0 0; color: #757575; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e0e0e0; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    .postupuje-ano, .postup-z-kraje-ano {{ color: #2e7d32; font-weight: bold; }}
    .postupuje-ne, .postup-z-kraje-ne {{ color: #c62828; }}
    .medal {{ display: inline-block; min-width: 18px; text-align: center; border-radius: 4px; margin-right: 4px; color: white; font-size: 12px; }}
    .gold {{ background: #f9a825; }}
    .silver {{ background: #90a4ae; }}
    .bronze {{ background: #8d6e63; }}
    .filters {{
      background: white; border-radius: 12px; padding: 16px 20px;
      margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .filters-row {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: end; }}
    .filter-field {{ display: flex; flex-direction: column; gap: 4px; min-width: 160px; flex: 1; }}
    .filter-field label {{ font-size: 12px; font-weight: 600; color: #555; text-transform: uppercase; }}
    .filter-field select, .filters button {{
      font: inherit; padding: 8px 10px; border: 1px solid #ccc; border-radius: 8px; background: white;
    }}
    .filters button {{ cursor: pointer; flex: 0; min-width: auto; }}
    .filter-checkboxes {{ display: flex; flex-wrap: wrap; gap: 20px; margin-top: 14px; }}
    .filter-checkboxes label {{
      display: flex; align-items: center; gap: 8px; font-size: 14px; color: #333; cursor: pointer;
    }}
    .filter-checkboxes input {{ width: 16px; height: 16px; cursor: pointer; }}
    .filter-checkboxes input:disabled + span {{ color: #999; cursor: not-allowed; }}
    .filter-status {{ margin-top: 12px; font-size: 14px; color: #555; }}
    .color-key {{
      background: white; border-radius: 12px; padding: 14px 20px 16px;
      margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      display: flex; flex-wrap: wrap; gap: 20px 40px; align-items: start;
    }}
    .color-key-block {{ min-width: 200px; }}
    .color-key .legend-subtitle {{ margin: 0 0 8px; }}
    .color-key .legend-swatches {{ margin-bottom: 0; }}
    tr.club-highlight {{ background: #e8f5e9; }}
    tr.club-highlight td {{ border-bottom-color: #c8e6c9; }}
    tr.club-highlight td:nth-child(3) {{ font-weight: 600; color: #2e7d32; }}
    .legend {{
      background: white; border-radius: 12px; padding: 20px 24px;
      margin-top: 32px; margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      scroll-margin-top: 24px;
    }}
    .legend h2 {{ margin: 0 0 8px; font-size: 20px; color: #3949ab; }}
    .legend-intro {{ margin: 0 0 12px; font-size: 14px; color: #555; }}
    .legend-subtitle {{ margin: 14px 0 8px; font-size: 13px; font-weight: 700; color: #555; text-transform: uppercase; }}
    .legend-swatches {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }}
    .swatch {{
      display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: #444;
      padding: 6px 10px; border-radius: 8px; border-left: 4px solid transparent; font-weight: 600;
    }}
    .swatch-discipline {{ font-weight: 700; }}
    .swatch-unofficial {{ background: #fff3e0; border-left: 4px solid #ef6c00; }}
    .swatch-empty {{ background: #fafafa; border: 1px dashed #bdbdbd; }}
    .swatch-filter {{
      font-family: inherit; cursor: pointer; border-top: 0; border-right: 0; border-bottom: 0;
      transition: opacity .15s, box-shadow .15s, transform .05s;
    }}
    .swatch-filter.swatch-empty {{ border: 1px dashed #bdbdbd; }}
    .swatch-filter:hover {{ box-shadow: 0 1px 4px rgba(0,0,0,0.18); }}
    .swatch-filter:active {{ transform: translateY(1px); }}
    .swatch-filter:focus-visible {{ outline: 2px solid #3949ab; outline-offset: 2px; }}
    .swatch-filter.swatch-active {{ box-shadow: 0 0 0 2px currentColor; }}
    .swatch-filter.swatch-dim {{ opacity: 0.45; }}
    .swatch-filter.swatch-off {{ opacity: 0.45; text-decoration: line-through; }}
    .legend dl {{ margin: 0; display: grid; gap: 12px; }}
    .legend dt {{ font-weight: 600; font-size: 14px; color: #222; }}
    .legend dd {{ margin: 4px 0 0; font-size: 14px; color: #444; line-height: 1.45; }}
    .copy-nomination-col {{ width: 44px; text-align: center; }}
    .copy-nomination-cell {{ width: 44px; text-align: center; }}
    .copy-nomination-btn {{
      min-width: 52px; height: 28px; padding: 0 6px; border: 1px solid #c5cae9; border-radius: 8px;
      background: #eef2ff; color: #3949ab; cursor: pointer; font-size: 11px; font-weight: 600; line-height: 1;
    }}
    .copy-nomination-btn:hover {{ background: #e8eaf6; }}
    .copy-nomination-btn.copy-nomination-ok {{ background: #c8e6c9; border-color: #81c784; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
    .tab-btn {{
      font: inherit; font-weight: 600; padding: 10px 18px; border-radius: 10px; cursor: pointer;
      border: 1px solid #c5cae9; background: white; color: #3949ab;
    }}
    .tab-btn:hover {{ background: #e8eaf6; }}
    .tab-btn.tab-active {{ background: #3949ab; border-color: #3949ab; color: white; }}
    .tab-count {{
      display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px;
      background: rgba(57,73,171,0.12); font-size: 12px;
    }}
    .tab-btn.tab-active .tab-count {{ background: rgba(255,255,255,0.25); }}
    [hidden] {{ display: none !important; }}
    .final-head {{
      background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .final-head h2 {{ margin: 0 0 6px; font-size: 22px; color: #3949ab; }}
    .final-intro {{ margin: 0 0 12px; font-size: 14px; color: #555; }}
    .final-controls {{ display: flex; flex-wrap: wrap; gap: 16px; align-items: end; }}
    .final-controls .filter-field {{ flex: 0 1 360px; }}
    .final-summary {{ margin: 0 0 8px; font-weight: 600; }}
    .final-list {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px;
    }}
    .final-discipline {{
      --disc-accent: #3949ab; --disc-bg: #e8eaf6;
      background: linear-gradient(90deg, var(--disc-bg) 0%, #ffffff 48px);
      border-left: 6px solid var(--disc-accent); border-radius: 12px;
      padding: 16px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .final-discipline-title {{ margin: 0 0 12px; font-size: 22px; color: var(--disc-accent); }}
    .final-discipline-title::before {{
      content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px;
      background: var(--disc-accent); margin-right: 8px; vertical-align: middle;
    }}
    .final-discipline-count {{ font-size: 14px; font-weight: normal; color: #777; }}
    .final-category {{
      background: white; border-radius: 12px; padding: 12px 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid var(--disc-accent);
    }}
    .final-category h3 {{ color: #222; }}
    .final-category table {{ table-layout: fixed; }}
    .final-col-name {{ width: 42%; }}
    .final-category h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .final-count {{ color: #777; font-weight: normal; font-size: 14px; }}
    .final-badge {{
      display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 6px;
      background: #fff3e0; color: #e65100; font-size: 11px; font-weight: 600; vertical-align: middle;
    }}
    .manual-edits {{
      background: white; border-radius: 12px; padding: 16px 20px; margin-top: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08); scroll-margin-top: 24px;
    }}
    .manual-edits h2 {{ margin: 0 0 6px; font-size: 20px; color: #3949ab; }}
    .me-list {{
      list-style: none; margin: 0; padding: 0; display: grid; gap: 12px;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    }}
    .me-card {{
      border: 1px solid #e0e0e0; border-left: 4px solid #3949ab; border-radius: 10px;
      padding: 12px 14px; background: #fafbff;
    }}
    .me-card.me-presun {{ border-left-color: #1e88e5; }}
    .me-card.me-pridat {{ border-left-color: #2e7d32; }}
    .me-card.me-odebrat {{ border-left-color: #c62828; }}
    .me-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
    .me-type {{
      font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
      padding: 2px 8px; border-radius: 6px; background: #e3f2fd; color: #1565c0;
    }}
    .me-pridat .me-type {{ background: #e8f5e9; color: #2e7d32; }}
    .me-odebrat .me-type {{ background: #ffebee; color: #c62828; }}
    .me-card.me-prestup {{ border-left-color: #6a1b9a; }}
    .me-prestup .me-type {{ background: #f3e5f5; color: #6a1b9a; }}
    .transfer-badge {{
      display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 6px;
      background: #f3e5f5; color: #6a1b9a; font-size: 11px; font-weight: 600;
      vertical-align: middle; cursor: help; white-space: nowrap;
    }}
    .transfer-from {{ font-weight: normal; }}
    .me-date {{ font-size: 12px; color: #777; }}
    .me-name {{ margin: 0 0 6px; font-weight: 700; font-size: 15px; }}
    .me-club {{ display: block; font-weight: normal; font-size: 13px; color: #666; }}
    .me-change {{ margin: 0 0 6px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 14px; }}
    .me-cat {{ background: #eef2ff; padding: 2px 8px; border-radius: 6px; }}
    .me-cat-old {{ text-decoration: line-through; color: #777; background: #f5f5f5; }}
    .me-arrow {{ font-weight: 700; color: #3949ab; }}
    .me-reason {{ margin: 0; font-size: 13px; color: #444; line-height: 1.4; }}
    @media (max-width: 520px) {{
      .container {{ padding: 16px; }}
      .final-list, .me-list {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{escape_html(tournament_name)}</h1>
      <div class="stats" id="header-stats">
        <span>Datum: {escape_html(tournament_date)}</span>
        <span>Zavodnici: {escape_html(competitors)}</span>
        <span>Starty: {escape_html(starts)}</span>
        <span>Kluby: {escape_html(clubs)}</span>
        <span>Kola: {escape_html(rounds)}</span>
      </div>
    </header>
    {login_html}
    <nav class="tabs" role="tablist">
      <button type="button" class="tab-btn tab-active" data-tab="results" role="tab" aria-selected="true">Výsledky</button>
      <button type="button" class="tab-btn" data-tab="final" role="tab" aria-selected="false">Finální postupující <span class="tab-count">{len(final_rows)}</span></button>
    </nav>
    {content_open}
    <section class="filters">
      <div class="filters-row">
        <div class="filter-field">
          <label for="filter-club">Klub</label>
          <select id="filter-club"><option value="">Vše</option></select>
        </div>
        <div class="filter-field">
          <label for="filter-main">Disciplína</label>
          <select id="filter-main"><option value="">Vše</option></select>
        </div>
        <div class="filter-field">
          <label for="filter-detail">Kategorie</label>
          <select id="filter-detail"><option value="">Vše</option></select>
        </div>
        <button type="button" id="filter-reset">Zrušit filtry</button>
      </div>
      <div class="filter-checkboxes">
        <label>
          <input type="checkbox" id="filter-only-club" disabled>
          <span>Jen vybraný klub</span>
        </label>
        <label>
          <input type="checkbox" id="filter-only-postup">
          <span>Jen postupy</span>
        </label>
        <label>
          <input type="checkbox" id="filter-only-remiza">
          <span>Jen remízy</span>
        </label>
        <label>
          <input type="checkbox" id="filter-show-unofficial" checked>
          <span>Zobrazit mimo offic. kategorie</span>
        </label>
        <label>
          <input type="checkbox" id="filter-show-empty" checked>
          <span>Zobrazit prázdné oficiální</span>
        </label>
      </div>
      <p class="filter-status" id="filter-status"></p>
    </section>
    {color_key_html}
    {''.join(discipline_html)}
    {legend_html}
    </div>
    {final_tab_html}
  </div>
{tail_scripts}
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generuje HTML prezentaci vysledku")
    parser.add_argument("--input", type=Path, default=AGGREGATED_XML)
    parser.add_argument("--csv", type=Path, default=EXCEL_CSV)
    parser.add_argument("--output", type=Path, default=PRESENTATION_HTML)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Chyba: {args.input} neexistuje")
        return 1
    if not args.csv.is_file():
        print(f"Chyba: {args.csv} neexistuje, spust nejprve excel export")
        return 1

    generate_html(args.input, args.csv, args.output)
    print(f"HTML prezentace: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
