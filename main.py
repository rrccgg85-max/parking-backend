import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
import pytesseract
import pypdf
import pillow_heif

# ลงทะเบียนรองรับภาพ HEIC จาก iPhone
pillow_heif.register_heif_opener()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "online", "mode": "standalone_ocr_v4"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        await file.seek(0)
        contents = await file.read()
        
        if not contents:
            return {"success": False, "error": "ไฟล์ที่อัปโหลดไม่มีข้อมูล", "amount": 0.0}

        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        extracted_text = ""

        # ตรวจสอบว่าเป็นไฟล์ PDF หรือไม่
        is_pdf = filename.endswith(".pdf") or "pdf" in content_type or contents.startswith(b"%PDF")

        if is_pdf:
            # 1. ประมวลผลไฟล์ PDF
            try:
                pdf_reader = pypdf.PdfReader(io.BytesIO(contents))
                
                # 1.1 อ่านข้อความจาก PDF ดั้งเดิม
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        extracted_text += text + "\n"

                # 1.2 หากเป็น Scanned PDF (ไม่มี Text) ให้แกะภาพใน PDF มาทำ OCR
                if not extracted_text.strip():
                    for page in pdf_reader.pages:
                        for img_file in page.images:
                            try:
                                image = Image.open(io.BytesIO(img_file.data))
                                if image.mode != "RGB":
                                    image = image.convert("RGB")
                                txt = pytesseract.image_to_string(image, lang='tha+eng')
                                extracted_text += txt + "\n"
                            except Exception as img_ocr_err:
                                print(f"Error OCR image inside PDF: {img_ocr_err}")
            except Exception as pdf_err:
                return {"success": False, "error": f"อ่านไฟล์ PDF ไม่สำเร็จ: {str(pdf_err)}", "amount": 0.0}

        else:
            # 2. ประมวลผลไฟล์รูปภาพ (JPG, PNG, WEBP, HEIC)
            try:
                image = Image.open(io.BytesIO(contents))
                if image.mode != "RGB":
                    image = image.convert("RGB")
                
                try:
                    extracted_text = pytesseract.image_to_string(image, lang='tha+eng')
                except Exception:
                    extracted_text = pytesseract.image_to_string(image, lang='eng')

            except UnidentifiedImageError:
                return {
                    "success": False, 
                    "error": "ไม่สามารถอ่านไฟล์รูปภาพนี้ได้ โปรดใช้อัปโหลดไฟล์ JPG, PNG หรือ PDF มาตรฐาน", 
                    "amount": 0.0
                }
            except Exception as img_err:
                return {
                    "success": False, 
                    "error": f"เปิดรูปภาพไม่สำเร็จ: {str(img_err)}", 
                    "amount": 0.0
                }

        # 3. ค้นหายอดเงินทศนิยม
        amount_matches = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', extracted_text)

        extracted_amount = 0.0
        if amount_matches:
            clean_amount = amount_matches[-1].replace(',', '')
            extracted_amount = float(clean_amount)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:300]
        }

    except Exception as e:
        print(f"General Error: {str(e)}")
        return {"success": False, "error": str(e), "amount": 0.0}