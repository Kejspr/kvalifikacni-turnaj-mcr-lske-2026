PYTHON ?= python3
SRC = src

DOCS = docs
FINAL_PDF = output/pdf/final-postupujici.pdf
CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
PAGES_URL = https://kejspr.github.io/kvalifikacni-turnaj-mcr-lske-2026/
PUBLISH_MSG ?= Aktualizace vysledku

.PHONY: help deploy deploy-site build pages validate fix aggregate excel verify-nominations final-export pdf git-push publish all vse deploy-pages

help:
	@echo "Kvalifikacni turnaj MCR Beginner - LSKe (GitHub Pages)"
	@echo ""
	@echo "  make deploy         kompletni WF: validate -> fix -> aggregate -> deploy-site + push"
	@echo "  make deploy-site    excel + final-export + PDF + HTML + verify-nominations (bez git push)"
	@echo ""
	@echo "Jednotlive kroky:"
	@echo "  make validate             kontrola original/"
	@echo "  make fix                  original/ -> pracovni/"
	@echo "  make aggregate            pracovni/ -> aggregated-results.xml"
	@echo "  make excel                CSV + Postupuje + nomination log"
	@echo "  make final-export         konecny seznam postupujicich (CSV, TSV, TXT, HTML)"
	@echo "  make pdf                  final-postupujici.pdf z HTML (Chrome headless)"
	@echo "  make pages                HTML -> docs/index.html (vyzaduje excel)"
	@echo "  make verify-nominations   kontrola nominations/*.txt"
	@echo ""
	@echo "Volitelne:"
	@echo "  make build          jen data: validate + fix + aggregate + excel"
	@echo ""
	@echo "Zpetna kompatibilita:"
	@echo "  make deploy-pages = make deploy"
	@echo "  make publish      = make deploy"
	@echo "  make vse          = make deploy"

deploy: validate fix aggregate deploy-site git-push
	@echo ""
	@echo "Deploy hotovo: $(PAGES_URL) (po dokonceni Actions)"

deploy-site: excel final-export pdf pages verify-nominations

build: validate fix aggregate excel
	@echo ""
	@echo "Build hotovo: pracovni/ + aggregated-results.xml + CSV"

pages:
	mkdir -p $(DOCS)
	$(PYTHON) $(SRC)/generate_presentation.py --output $(DOCS)/index.html
	@echo ""
	@echo "HTML: $(DOCS)/index.html"

validate:
	$(PYTHON) $(SRC)/validate_data.py

fix:
	$(PYTHON) $(SRC)/fix_xml_data.py

aggregate:
	$(PYTHON) $(SRC)/aggregate_results.py

excel:
	$(PYTHON) $(SRC)/generate_excel_export.py

final-export: excel
	$(PYTHON) $(SRC)/generate_final_export.py

# PDF finalniho seznamu - tisk final-postupujici.html pres Chrome bez okna
pdf: final-export
	@if [ ! -x "$(CHROME)" ]; then \
		echo "Chrome nenalezen ($(CHROME)) - PDF vytiskni rucne z final-postupujici.html"; \
	else \
		mkdir -p $(dir $(FINAL_PDF)); \
		"$(CHROME)" --headless=new --disable-gpu --no-pdf-header-footer \
			--print-to-pdf="$(CURDIR)/$(FINAL_PDF)" "file://$(CURDIR)/final-postupujici.html" >/dev/null 2>&1; \
		cp $(FINAL_PDF) final-postupujici.pdf; \
		echo "PDF: $(FINAL_PDF) (+ kopie final-postupujici.pdf)"; \
	fi

verify-nominations:
	$(PYTHON) $(SRC)/verify_categories.py

git-push:
	@if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		echo "Chyba: neni git repo"; exit 1; \
	fi
	git add docs/index.html original/ nominations/ nominations-declined/ rucni-upravy.txt $(FINAL_PDF) final-postupujici.pdf src/ Makefile .github/
	@if git diff --staged --quiet; then \
		echo "Nic k publikovani - zadne zmeny"; \
	else \
		git commit -m "$(PUBLISH_MSG)"; \
		git push origin HEAD; \
		echo "Odeslano na GitHub."; \
	fi

deploy-pages: deploy

publish: deploy

vse: deploy

all: build pages

.DEFAULT_GOAL := help
