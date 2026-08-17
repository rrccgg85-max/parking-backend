import os
import json
import re
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

app = FastAPI(title="Parking Slip Extractor API", version="2.0.0")

# รองรับ CORS สำหรับการเชื่อมต่อจาก Frontend ทุกโดเมน
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class ExtractResponse(BaseModel):
    success: bool
    amount: float
    filename: str
    message: str = ""
    error: str = ""

@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "Parking Slip Extractor",
        "api_key_configured": bool(GEMINI_API_KEY)
    }

@app.post("/extract", response_model=ExtractResponse)
async def extract_amount(file: UploadFile = File(...)):
    if not GEMINI_API_KEY:
        print("CRITICAL ERROR: GEMINI_API_KEY Environment Variable is missing!")
        return ExtractResponse(
            success=False,
            amount=0.0,
            filename=file.filename or "unknown",
            error="Server missing GEMINI_API_KEY configuration."
        )

    try:
        contents = await file.read()
        if not contents or len(contents) == 0:
            return ExtractResponse(
                success=False,
                amount=0.0,
                filename=file.filename or "unknown",
                error="Uploaded file is empty."
            )

        # ระบุ MIME Type ของไฟล์ที่อัปโหลด
        filename_lower = (file.filename or "").lower()
        if filename_lower.endswith(".pdf"):
            mime_type = "application/pdf"
        elif filename_lower.endswith(".png"):
            mime_type = "image/png"
        elif filename_lower.endswith(".webp"):
            mime_type = "image/webp"
        elif filename_lower.endswith(".heic"):
            mime_type = "image/heic"
        else:
            mime_type = file.content_type if file.content_type and "image" in file.content_type else "image/jpeg"

        print(f"[INFO] Processing file: '{file.filename}' (Size: {len(contents)} bytes, Mime: {mime_type})")

        # เรียกใช้ Gemini SDK
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = (
            "You are an expert OCR receipt parser. Analyze the provided image or PDF receipt/slip.\n"
            "Extract the final total paid amount (such as รวมทั้งสิ้น, ยอดชำระ, Net Total, Total Paid, Amount).\n"
            "Output MUST be strict JSON in this format: {\"amount\": 150.00}\n"
            "If no valid amount is found or readable, set amount to 0.0."
        )

        # เรียกใช้โมเดล gemini-2.5-flash ผ่าน SDK Standard
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=contents,
                    mime_type=mime_type,
                ),
                prompt
            ]
        )

        res_text = response.text.strip() if response.text else ""
        print(f"[DEBUG] Gemini Raw Output: {res_text}")

        # ดึง JSON จากข้อความตอบกลับ
        extracted_amount = 0.0
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                extracted_amount = float(data.get("amount", 0.0))
            except (json.JSONDecodeError, ValueError) as parse_err:
                print(f"[WARN] Failed to parse JSON: {parse_err}")

        is_success = extracted_amount > 0.0
        return ExtractResponse(
            success=is_success,
            amount=extracted_amount,
            filename=file.filename or "unknown",
            message="Extracted successfully" if is_success else "Amount not found in receipt"
        )

    except Exception as e:
        print(f"[ERROR] Exception occurred: {str(e)}")
        return ExtractResponse(
            success=False,
            amount=0.0,
            filename=file.filename or "unknown",
            error=str(e)
        )