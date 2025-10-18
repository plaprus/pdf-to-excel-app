from __future__ import annotations
import io
import os
from dataclasses import dataclass
from typing import List, Tuple
import streamlit as st
import pandas as pd

# Funkcja poprawiająca nazwy kolumn, żeby się nie powtarzały
def make_unique_headers(columns):
    seen = {}
    fixed = []
    for c in columns:
        name = "" if c is None else str(c).strip()
        if name == "":
            name = "col"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        fixed.append(name)
    return fixed


# Optional libraries
enable_pdfplumber = True
try:
    import pdfplumber  # type: ignore
except Exception:
    enable_pdfplumber = False

enable_ocr = True
try:
    from pdf2image import convert_from_bytes  # type: ignore
    import pytesseract  # type: ignore
    from PIL import Image  # noqa: F401
except Exception:
    enable_ocr = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_OK = True
except Exception:
    PYMUPDF_OK = False


@dataclass
class ExtractedContent:
    text_pages: List[str]
    tables: List[pd.DataFrame]
    table_meta: List[Tuple[int, int]]  # (page_index, table_index_within_page)


def extract_with_pdfplumber(file_bytes: bytes) -> ExtractedContent:
    text_pages: List[str] = []
    tables: List[pd.DataFrame] = []
    table_meta: List[Tuple[int, int]] = []

    if not enable_pdfplumber:
        return ExtractedContent(text_pages=[], tables=[], table_meta=[])

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            # Text extraction
            try:
                text = page.extract_text(x_tolerance=1, y_tolerance=2) or ""
            except Exception:
                text = ""
            text_pages.append(text)

            # Table extraction strategies
            page_tables = []
            try:
                page_tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "edge_min_length": 3,
                        "min_words_vertical": 3,
                        "min_words_horizontal": 3,
                        "keep_blank_chars": False,
                    }
                )
            except Exception:
                page_tables = []

            if not page_tables:
                try:
                    page_tables = page.extract_tables(
                        table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "snap_tolerance": 3,
                            "join_tolerance": 3,
                        }
                    )
                except Exception:
                    page_tables = []

            for t_idx, table in enumerate(page_tables or []):
                try:
                    df = pd.DataFrame(table)
                    if not df.empty and df.iloc[0].isna().sum() == 0:
                        df.columns = df.iloc[0]
                        df = df[1:].reset_index(drop=True)
                        df.columns = make_unique_headers(df.columns)
                except Exception:
                    continue
                tables.append(df)
                table_meta.append((p_idx, t_idx))

    return ExtractedContent(text_pages=text_pages, tables=tables, table_meta=table_meta)


def ocr_pdf_to_text(file_bytes: bytes, lang: str = "pol+eng") -> List[str]:
    if not enable_ocr:
        return []
    try:
        images = convert_from_bytes(file_bytes, dpi=300)
        texts: List[str] = []
        for im in images:
            txt = pytesseract.image_to_string(im, lang=lang)
            texts.append(txt)
        return texts
    except Exception:
        return []


def save_to_excel(content: ExtractedContent, include_aggregate: bool = True) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        text_df = pd.DataFrame({
            "page": list(range(1, len(content.text_pages) + 1)),
            "text": content.text_pages,
        })
        text_df.to_excel(writer, index=False, sheet_name="Text")

        for (p_idx, t_idx), df in zip(content.table_meta, content.tables):
            sheet_name = f"P{p_idx+1}_T{t_idx+1}"[:31]
            df.to_excel(writer, index=False, sheet_name=sheet_name)

        if include_aggregate and content.tables:
            agg = []
            for (p_idx, t_idx), df in zip(content.table_meta, content.tables):
                df_copy = df.copy()
                df_copy.insert(0, "page", p_idx + 1)
                df_copy.insert(1, "table", t_idx + 1)
                agg.append(df_copy)
            agg_df = pd.concat(agg, ignore_index=True)
            agg_df.to_excel(writer, index=False, sheet_name="All_Tables")

    output.seek(0)
    return output.read()


def detect_scanned(text_pages: List[str]) -> bool:
    if not text_pages:
        return True
    non_empty = sum(1 for t in text_pages if (t or "").strip())
    ratio = non_empty / max(1, len(text_pages))
    return ratio < 0.2


# -------------------------- UI --------------------------
st.set_page_config(page_title="PDF → Excel Converter", page_icon="📄➡️📊", layout="centered")
st.title("📄 → 📊 PDF → Excel Converter")
st.caption("Wczytaj PDF-y, a ja wyciągnę tekst i tabele do pliku .xlsx.")

with st.expander("⚙️ Ustawienia"):
    ocr_toggle = st.checkbox("Włącz OCR (dla skanów / zdjęć)", value=False, disabled=not enable_ocr)
    ocr_lang = st.text_input("Języki OCR (kody Tesseract)", value="pol+eng", help="Np. pol, eng, deu. Wymaga zainstalowanych pakietów językowych Tesseract.")
    aggregate = st.checkbox("Dodaj arkusz zbiorczy 'All_Tables'", value=True)

uploaded = st.file_uploader("Przeciągnij i upuść pliki PDF (wiele dozwolone)", type=["pdf"], accept_multiple_files=True)

if uploaded:
    for up in uploaded:
        st.subheader(f"Plik: {up.name}")
        file_bytes = up.read()

        content = extract_with_pdfplumber(file_bytes)

        if ocr_toggle and detect_scanned(content.text_pages):
            with st.spinner("Uruchamianie OCR — to może potrwać w zależności od liczby stron…"):
                ocr_texts = ocr_pdf_to_text(file_bytes, lang=ocr_lang)
                if ocr_texts:
                    content.text_pages = ocr_texts

        xlsx_bytes = save_to_excel(content, include_aggregate=aggregate)
        out_basename = os.path.splitext(os.path.basename(up.name))[0] or "output"

        st.success(f"Gotowe! Wyodrębniono {len(content.text_pages)} stron tekstu oraz {len(content.tables)} tabel.")
        st.download_button(
            label="⬇️ Pobierz plik Excel",
            data=xlsx_bytes,
            file_name=f"{out_basename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if content.tables:
            st.markdown("**Podgląd pierwszej wykrytej tabeli:**")
            preview = content.tables[0].copy()
            preview.columns = make_unique_headers(preview.columns)
            st.dataframe(preview.head(20), use_container_width=True)

        else:
            st.info("Nie wykryto tabel. Jeśli to skan, spróbuj włączyć OCR lub dostosować parametry.")

        if any((t or "").strip() for t in content.text_pages):
            st.markdown("**Podgląd tekstu z pierwszej strony:**")
            st.code((content.text_pages[0] or "").strip()[:3000] or "(brak tekstu)")
        else:
            st.warning("Nie wykryto tekstu. Włącz OCR, jeśli to skanowany dokument.")
# -------------------------- PRO MODE: Zdjęcie → Excel (wysoka jakość) --------------------------
# Ten tryb pozwala wgrać zdjęcie lub skan tabeli i zamienić je w plik Excel (.xlsx)

import tempfile
from typing import Dict

PRO_MODE_AVAILABLE = False
try:
    from paddleocr import PPStructure
    import cv2
    import numpy as np
    PRO_MODE_AVAILABLE = True
except Exception:
    PRO_MODE_AVAILABLE = False

def pro_extract_tables_from_image(image_bytes: bytes) -> Dict[str, bytes]:
    """Tworzy plik Excel z tabeli wykrytej na zdjęciu."""
    if not PRO_MODE_AVAILABLE:
        return {}

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "input.png")
        with open(img_path, "wb") as f:
            f.write(image_bytes)

        table_engine = PPStructure(show_log=False, layout=False)
        result = table_engine(img_path)

        outputs: Dict[str, bytes] = {}
        for fname in os.listdir(tmp):
            if fname.lower().endswith(".xlsx"):
                full = os.path.join(tmp, fname)
                with open(full, "rb") as xf:
                    outputs[fname] = xf.read()
        return outputs

# UI: sekcja dla PRO trybu (zdjęcia)
with st.expander("🧪 PRO: Zdjęcie/Skany → Excel (PP-Structure)"):
    st.caption("Użyj tego trybu, jeśli masz zdjęcie lub skan tabeli — najlepsza jakość odwzorowania.")
    if not PRO_MODE_AVAILABLE:
        st.warning("Tryb PRO wymaga dodatkowych pakietów: paddleocr, paddlepaddle, opencv-python. Użyj Dockera lub lokalnej instalacji.")
    img_files = st.file_uploader("Wgraj zdjęcia (JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if img_files and PRO_MODE_AVAILABLE:
        for img in img_files:
            st.subheader(f"Obraz: {img.name}")
            data = img.read()
            with st.spinner("Analizuję obraz i tworzę plik Excel..."):
                excel_map = pro_extract_tables_from_image(data)
            if not excel_map:
                st.error("Nie udało się utworzyć pliku .xlsx — upewnij się, że tabela jest wyraźna i prosta.")
            else:
                for fname, blob in excel_map.items():
                    st.success(f"Gotowy plik: {fname}")
                    st.download_button(
                        label=f"⬇️ Pobierz {fname}",
                        data=blob,
                        file_name=fname,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
