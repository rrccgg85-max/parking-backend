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
            print("Error: GEMINI_API_KEY is not set")
            return {"success": False, "error": "GEMINI_API_KEY is not set", "amount": 0.0}

        contents = await file.read()
        if not contents:
            return {"success": False, "error": "Uploaded file is empty", "amount": 0.0}

        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            mime_type = "application/pdf"
        elif filename_lower.endswith(".png"):
            mime_type = "image/png"
        elif filename_lower.endswith(".webp"):
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"

        print(f"Processing file: {file.filename} with mime_type: {mime_type}")

        # เรียกใช้ SDK ล่าสุด
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = (
            "Analyze this receipt or slip image/PDF carefully and extract the final total paid amount "
            "(เช่น จำนวนเงิน, ยอดชำระ, รวมทั้งสิ้น, Net Total, Grand Total).\n"
            "Respond ONLY with a valid JSON object matching this exact format: {\"amount\": 150.00}.\n"
            "If no amount can be extracted or found, return {\"amount\": 0.0}."
        )

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

        res_text = response.text.strip()
        print(f"Gemini Raw Response: {res_text}")

        match = re.search(r'\{.*\}', res_text, re.DOTALL)
        if match:
            json_str = match.group()
            data = json.loads(json_str)
            extracted_amount = float(data.get("amount", 0.0))
        else:
            extracted_amount = 0.0

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename
        }

    except Exception as e:
        print(f"General Error: {str(e)}")
        return {"success": False, "error": str(e), "amount": 0.0}