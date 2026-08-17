import io
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import pytesseract

app = FastAPI()

# ตั้งค่า CORS รองรับการเรียกจาก Frontend ทุกที่
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "online", "mode": "standalone_ocr"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        # รีเซ็ตเคอร์เซอร์ไฟล์ไปยังจุดเริ่มต้นก่อนอ่านข้อมูล
        await file.seek(0)
        contents = await file.read()
        
        if not contents:
            return {"success": False, "error": "File is empty", "amount": 0.0}

        # โหลดไฟล์ภาพจาก Bytes
        image = Image.open(io.BytesIO(contents))
        
        # ถอดข้อความด้วย Tesseract OCR (ลองใช้ทั้งไทย+อังกฤษ หากไม่มีภาษาไทยจะสลับเป็น eng ให้อัตโนมัติ)
        try:
            extracted_text = pytesseract.image_to_string(image, lang='tha+eng')
        except Exception:
            extracted_text = pytesseract.image_to_string(image, lang='eng')

        # ค้นหารูปแบบตัวเลขทศนิยม เช่น 150.00 หรือ 1,250.50
        amount_matches = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', extracted_text)

        extracted_amount = 0.0
        if amount_matches:
            # ดึงทศนิยมตัวสุดท้ายที่พบในสลิป (มักเป็นยอดเงินสรุปสุทธิ)
            clean_amount = amount_matches[-1].replace(',', '')
            extracted_amount = float(clean_amount)

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename,
            "raw_text": extracted_text[:300]  # ตัวอย่างข้อความที่แกะออกมาได้
        }

    except Exception as e:
        print(f"Error processing image: {str(e)}")
        return {"success": False, "error": str(e), "amount": 0.0}