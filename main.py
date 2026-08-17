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

def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """ปรับความคมชัดและแปลงเป็น ขาว-ดำ เพื่อให้ Tesseract แกะตัวอักษรสีฟ้า/หนาได้แม่นยำขึ้น"""
    img = img.convert("L")  # แปลงเป็น Grayscale
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(2.0)  # เพิ่ม Contrast 2 เท่า

def parse_amount_from_text(text: str) -> float:
    if not text:
        return 0.0

    # 1. ทำความสะอาดช่องว่างส่วนเกินที่ OCR มักทำหลุด เช่น '4 0 . 0 0' -> '40.00'
    cleaned = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    cleaned = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', cleaned)

    # 2. Regex ค้นหาตามลำดับความสำคัญ
    patterns = [
        r'รวมทั้งสิ้น\s*([0-9,]+(?:\.[0-9]{2})?)',           # เช่น "รวมทั้งสิ้น 40.00"
        r'([0-9,]+(?:\.[0-9]{2})?)\s*บาท',                   # เช่น "40.00 บาท"
        r'(?:ยอดชำระ|สุทธิ|total|amount)[\s:]*([0-9,]+(?:\.[0-9]{2})?)', # คำสำคัญอื่นๆ
        r'(\d{1,3}(?:,\d{3})*\.\d{2})'                       # ตัวเลขทศนิยม .XX ทั่วไป
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
    return {"status": "online", "mode": "standalone_ocr_v6"}

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
            # 1. ดึงข้อความดิจิทัลจาก PDF ก่อน
            try:
                pdf_reader = pypdf.PdfReader(io.BytesIO(contents))
                for page in pdf_reader.pages:
                    t = page.extract_text()
                    if t:
                        extracted_text += t + "\n"
            except Exception as e:
                print(f"pypdf extract error: {e}")

            # 2. Render หน้า PDF เป็นรูปภาพความละเอียดสูง (3x) + Preprocessing + OCR
            try:
                pdf_doc = pdfium.PdfDocument(contents)
                for page in pdf_doc:
                    pil_img = page.render(scale=3).to_pil()
                    processed_img = preprocess_image_for_ocr(pil_img)
                    
                    try:
                        ocr_t = pytesseract.image_to_string(processed_img, lang='tha+eng', config='--psm 6')
                    except Exception:
                        ocr_t = pytesseract.image_to_string(processed_img, lang='eng', config='--psm 6')
                    
                    extracted_text += "\n" + ocr_t
            except Exception as pdfium_err:
                print(f"pdfium render error: {pdfium_err}")

        else:
            # 3. กรณีเป็นไฟล์รูปภาพ (JPG, PNG, HEIC)
            try:
                image = Image.open(io.BytesIO(contents))
                if image.mode != "RGB":
                    image = image.convert("RGB")
                
                processed_img = preprocess_image_for_ocr(image)
                
                try:
                    extracted_text = pytesseract.image_to_string(processed_img, lang='tha+eng', config='--psm 6')
                except Exception:
                    extracted_text = pytesseract.image_to_string(processed_img, lang='eng', config='--psm 6')
            except UnidentifiedImageError:
                return {"success": False, "error": "รูปแบบรูปภาพไม่ถูกต้อง", "amount": 0.0}

        # สกัดยอดเงินจากข้อความที่ได้
        extracted_amount = parse_amount_from_text(extracted_text)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:300]
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}