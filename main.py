import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import pytesseract

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
    return {"status": "online"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        if not contents:
            return {"success": False, "error": "File is empty", "amount": 0.0}

        # อ่านรูปภาพด้วย Pillow
        image = Image.open(io.BytesIO(contents))

        # แปลงภาพเป็นข้อความ (อ่านทั้งภาษาไทยและอังกฤษ)
        extracted_text = pytesseract.image_to_string(image, lang='tha+eng')

        # ค้นหาแพทเทิร์นตัวเลขทศนิยม (เช่น 150.00 หรือ 1,250.50)
        # มุ่งเป้าบรรทัดที่มีคำว่า จำนวนเงิน / Baht / Total หรือตัวเลขท้ายๆ สลิป
        amount_matches = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', extracted_text)

        extracted_amount = 0.0
        if amount_matches:
            # ดึงตัวเลขทศนิยมตัวสุดท้ายที่พบในสลิป (ซึ่งมักจะเป็นยอดเงินสุทธิ)
            clean_amount = amount_matches[-1].replace(',', '')
            extracted_amount = float(clean_amount)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:200] # ส่งข้อความตัวอย่างกลับไปดูดิบๆ ได้
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}