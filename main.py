import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
import pytesseract
import pypdf
import pypdfium2 as pdfium
import pillow_heif

pillow_heif.register_heif_opener()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_amount_from_text(text: str) -> float:
    if not text:
        return 0.0

    # รวมตัวเลขที่ถูกแยกช่องว่าง เช่น '4 0 . 0 0' -> '40.00'
    cleaned_text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    cleaned_text = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', cleaned_text)

    # 1. ค้นหาตัวเลขที่อยู่ใกล้คำสำคัญ (รวมทั้งสิ้น, รวม, ยอดชำระ, Total, บาท)
    keyword_patterns = [
        r'(?:รวมทั้งสิ้น|รวมสุทธิ|รวม|ยอดชำระ|สุทธิ|total|amount|paid)[\s:]*([0-9,]+(?:\.[0-9]{2})?)',
        r'([0-9,]+(?:\.[0-9]{2})?)\s*(?:บาท|baht)'
    ]

    for pattern in keyword_patterns:
        matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
        if matches:
            for match in reversed(matches):
                try:
                    val = float(match.replace(',', ''))
                    if val > 0:
                        return val
                except ValueError:
                    continue

    # 2. ค้นหาตัวเลขทศนิยมทั่วไป (.XX)
    general_matches = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', cleaned_text)
    if general_matches:
        for match in reversed(general_matches):
            try:
                val = float(match.replace(',', ''))
                if val > 0:
                    return val
            except ValueError:
                continue

    return 0.0

@app.get("/")
def read_root():
    return {"status": "online", "mode": "standalone_ocr_v5"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        await file.seek(0)
        contents = await file.read()

        if not contents:
            return {"success": False, "error": "ไฟล์ไม่มีข้อมูล", "amount": 0.0}

        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        extracted_text = ""

        is_pdf = filename.endswith(".pdf") or "pdf" in content_type or contents.startswith(b"%PDF")

        if is_pdf:
            # 1. ดึงข้อความดิบจาก PDF
            try:
                pdf_reader = pypdf.PdfReader(io.BytesIO(contents))
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        extracted_text += t + "\n"
            except Exception as e:
                print(f"pypdf extract error: {e}")

            # 2. Render หน้า PDF เป็นรูปภาพเพื่อรัน OCR ซ้ำอีกรอบ (กันเหนียวสำหรับ Vector PDF/Scanned PDF)
            try:
                pdf_doc = pdfium.PdfDocument(contents)
                for page in pdf_doc:
                    pil_image = page.render(scale=2).to_pil()
                    try:
                        ocr_t = pytesseract.image_to_string(pil_image, lang='tha+eng')
                    except Exception:
                        ocr_t = pytesseract.image_to_string(pil_image, lang='eng')
                    extracted_text += "\n" + ocr_t
            except Exception as pdfium_err:
                print(f"pdfium render error: {pdfium_err}")

        else:
            # 3. กรณีเป็นไฟล์รูปภาพปกติ
            try:
                image = Image.open(io.BytesIO(contents))
                if image.mode != "RGB":
                    image = image.convert("RGB")
                try:
                    extracted_text = pytesseract.image_to_string(image, lang='tha+eng')
                except Exception:
                    extracted_text = pytesseract.image_to_string(image, lang='eng')
            except UnidentifiedImageError:
                return {"success": False, "error": "รูปแบบรูปภาพไม่ถูกต้อง", "amount": 0.0}

        # แกะยอดเงินจากข้อความ
        extracted_amount = parse_amount_from_text(extracted_text)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:300]
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}