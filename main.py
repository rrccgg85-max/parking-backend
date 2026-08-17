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

        client = genai.Client(api_key=GEMINI_API_KEY)

        # รายชื่อโมเดลมาตรฐานที่ใช้งานได้แน่นอน (ตัด gemini-2.5-flash ออก)
        candidate_models = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro"
        ]

        prompt = (
            "Extract the final total paid amount from this receipt/slip. "
            "Return ONLY a JSON object: {\"amount\": 150.00}. If not found, return {\"amount\": 0.0}."
        )

        response = None
        last_error = ""

        # รันยิง API จริงทีละโมเดล หากโมเดลไหนเกิด error จะสลับไปตัวถัดไปทันที
        for model_name in candidate_models:
            try:
                print(f"[TRYING] Model: {model_name}")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=contents, mime_type=mime_type),
                        prompt
                    ]
                )
                if response and response.text:
                    print(f"[SUCCESS] Successfully processed with model: {model_name}")
                    break
            except Exception as e:
                last_error = str(e)
                print(f"[FAIL] Model {model_name} failed: {last_error}")
                continue

        if not response or not response.text:
            return {"success": False, "error": f"All models failed. Last error: {last_error}", "amount": 0.0}

        res_text = response.text.strip()
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