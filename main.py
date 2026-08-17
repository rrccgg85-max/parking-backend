import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageEnhance, UnidentifiedImageError
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

def prepare_image(img: Image.Image) -> Image.Image:
    """แปลงภาพที่มี Alpha Channel (โปร่งใส) ให้มีพื้นหลังสีขาวเสมอ ป้องกันภาพดำสนิท"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")

def parse_amount_from_text(text: str) -> float:
    if not text:
        return 0.0

    # รวมช่องว่างที่โดนแยก เช่น '4 0 . 0 0' -> '40.00'
    cleaned = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    cleaned = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', cleaned)

    patterns = [
        r'รวมทั้งสิ้น\s*([0-9,]+(?:\.[0-9]{2})?)',
        r'([0-9,]+(?:\.[0-9]{2})?)\s*บาท',
        r'(?:ยอดชำระ|สุทธิ|total|amount)[\s:]*([0-9,]+(?:\.[0-9]{2})?)',
        r'(\d{1,3}(?:,\d{3})*\.\d{2})'
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

    return 0.0

@app.get("/")
def read_root():
    return {"status": "online", "mode": "standalone_ocr_v7"}

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
            # 1. อ่าน Text ดั้งเดิมจาก PDF
            try:
                pdf_reader = pypdf.PdfReader(io.BytesIO(contents))
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        extracted_text += t + "\n"
            except Exception as e:
                print(f"pypdf error: {e}")

            # 2. Render หน้า PDF เป็นรูปภาพ + ใส่พื้นหลังสีขาว + OCR
            try:
                pdf_doc = pdfium.PdfDocument(contents)
                for page in pdf_doc:
                    raw_pil = page.render(scale=3).to_pil()
                    img = prepare_image(raw_pil)
                    
                    try:
                        txt = pytesseract.image_to_string(img, lang='tha+eng')
                    except Exception:
                        txt = pytesseract.image_to_string(img, lang='eng')
                    
                    if txt.strip():
                        extracted_text += "\n" + txt
            except Exception as pdfium_err:
                print(f"pdfium error: {pdfium_err}")

        else:
            # 3. กรณีเป็นไฟล์รูปภาพ
            try:
                raw_img = Image.open(io.BytesIO(contents))
                img = prepare_image(raw_img)
                try:
                    extracted_text = pytesseract.image_to_string(img, lang='tha+eng')
                except Exception:
                    extracted_text = pytesseract.image_to_string(img, lang='eng')
            except UnidentifiedImageError:
                return {"success": False, "error": "รูปแบบรูปภาพไม่ถูกต้อง", "amount": 0.0}

        extracted_amount = parse_amount_from_text(extracted_text)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:300]
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}