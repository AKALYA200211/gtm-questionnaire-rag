import pandas as pd
import pdfplumber
import io

def parse_questionnaire(file_bytes: bytes, filename: str):
    name = filename.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
        return [str(q).strip() for q in df["Question"].dropna().tolist()]

    if name.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(file_bytes))
        return [str(q).strip() for q in df["Question"].dropna().tolist()]

    if name.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)

        questions = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[:2].isdigit() or line.startswith(("1.", "2.", "3.", "Q")):
                questions.append(line)
        return questions

    raise ValueError("Unsupported questionnaire format. Use CSV/XLSX/PDF.")