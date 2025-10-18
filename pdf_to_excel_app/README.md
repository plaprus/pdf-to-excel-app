# PDF → Excel Converter (Streamlit)

Konwerter PDF → XLSX z ekstrakcją tekstu i tabel. Obsługa OCR (Tesseract + pdf2image) dla skanów.

## Uruchomienie lokalnie
```bash
pip install -r requirements.txt
streamlit run app.py
```

## OCR (skany)
Zainstaluj Tesseract i Poppler (Windows: zobacz wiki Tesseract i repo Poppler dla Windows).

## Deploy na Streamlit Cloud
1. Wgraj repo na GitHub (ten folder).
2. Na https://streamlit.io utwórz nową aplikację wskazując `app.py`.
3. Gotowe — przekaż publiczny link.

## Docker
```bash
docker build -t pdf2xlsx .
docker run --rm -p 8501:8501 pdf2xlsx
```

## EXE (Windows, opcjonalnie)
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name PDF2Excel launch_streamlit.py
```
