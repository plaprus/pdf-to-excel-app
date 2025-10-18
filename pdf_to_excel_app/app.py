from __future__ import annotations
import io
import os
from dataclasses import dataclass
from typing import List, Tuple
import streamlit as st
import pandas as pd

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
            st.dataframe(content.tables[0].head(20), use_container_width=True)
        else:
            st.info("Nie wykryto tabel. Jeśli to skan, spróbuj włączyć OCR lub dostosować parametry.")

        if any((t or "").strip() for t in content.text_pages):
            st.markdown("**Podgląd tekstu z pierwszej strony:**")
            st.code((content.text_pages[0] or "").strip()[:3000] or "(brak tekstu)")
        else:
            st.warning("Nie wykryto tekstu. Włącz OCR, jeśli to skanowany dokument.")
