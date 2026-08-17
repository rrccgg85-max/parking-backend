import os
import json
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

@app.get("/")
def read_root():
    return {"status": "online"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        if not GEMINI_API_KEY:
            return {"success": False, "error": "GEMINI_API_KEY is missing", "amount": 0.0}

        contents = await file.read()
        if not contents:
            return {"success": False, "error": "File is empty", "amount": 0.0}

        filename_lower = (file.filename or "").lower()
        if filename_lower.endswith(".pdf"):
            mime_type = "application/pdf"
        elif filename_lower.endswith(".png"):
            mime_type = "image/png"
        elif filename_lower.endswith(".webp"):
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

        # เรียกใช้ Client จาก SDK ใหม่
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = (
            "Extract the final total paid amount from this receipt/slip. "
            "Return ONLY a JSON object: {\"amount\": 150.00}. If not found, return {\"amount\": 0.0}."
        )

        # ใช้ gemini-2.5-flash ซึ่งเป็นโมเดลมาตรฐานหลัก
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
        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        
        if match:
            data = json.loads(match.group())
            extracted_amount = float(data.get("amount", 0.0))
        else:
            extracted_amount = 0.0

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"success": False, "error": str(e), "amount": 0.0}