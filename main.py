import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import fitz  # PyMuPDF

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    extracted = ""
    
    # 1. ใช้ pdfplumber แกะโครงสร้าง Layout ภาษาไทยของใบเสร็จระบบเว็บ
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=True) or page.extract_text()
                if text:
                    extracted += text + "\n"
    except Exception as e:
        print(f"pdfplumber error: {e}")

    # 2. สำรองด้วย PyMuPDF (fitz) กรณี pdfplumber ดึงไม่ได้
    if not extracted.strip():
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                text = page.get_text("text", sort=True)
                if text:
                    extracted += text + "\n"
        except Exception as e:
            print(f"fitz error: {e}")

    return extracted

def parse_amount(text: str) -> float:
    if not text:
        return 0.0

    # จัดการช่องว่างระหว่างตัวเลข เช่น '4 0 . 0 0' -> '40.00'
    cleaned = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    cleaned = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', cleaned)

    # ค้นหาคำว่า "รวมทั้งสิ้น", "บาท" หรือตัวเลขทศนิยมยอดสุดท้าย
    patterns = [
        r'รวมทั้งสิ้น\s*([0-9,]+(?:\.[0-9]{2})?)',
        r'([0-9,]+(?:\.[0-9]{2})?)\s*บาท',
        r'(?:รวม|ยอดชำระ|สุทธิ)[\s:]*([0-9,]+(?:\.[0-9]{2})?)'
    ]

    for pattern in patterns:
        matches = re.findall(pattern, cleaned, re.IGNORECASE)
        if matches:
            for match in reversed(matches):
                try:
                    val = float(match.replace(',', ''))
                    if val > 0:
                        return val
                except ValueError:
                    continue

    # หากไม่พบคำสำคัญ ให้ดึงทศนิยมตัวสุดท้ายในเอกสาร
    all_decimals = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', cleaned)
    if all_decimals:
        try:
            return float(all_decimals[-1].replace(',', ''))
        except ValueError:
            pass

    return 0.0

@app.get("/")
def read_root():
    return {"status": "online", "mode": "pdfplumber_standalone"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        await file.seek(0)
        contents = await file.read()

        if not contents:
            return {"success": False, "error": "ไฟล์ไม่มีข้อมูล", "amount": 0.0}

        filename = (file.filename or "").lower()
        extracted_text = ""

        # ประมวลผลไฟล์ PDF
        if filename.endswith(".pdf") or contents.startswith(b"%PDF"):
            extracted_text = extract_text_from_pdf(contents)

        # คำนวณยอดเงิน
        amount = parse_amount(extracted_text)

        return {
            "success": True if amount > 0 else False,
            "amount": amount,
            "filename": file.filename,
            "raw_text": extracted_text[:500] if extracted_text.strip() else "ไม่พบข้อความในไฟล์"
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}