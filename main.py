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

@app.get("/list-models")
def list_models():
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY missing"}
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = [m.name for m in client.models.list()]
        return {"available_models": models}
    except Exception as e:
        return {"error": str(e)}

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

        # 1. ค้นหารายชื่อโมเดลจริงที่ API Key นี้รองรับให้อัตโนมัติ
        model_to_use = None
        try:
            available_models = [m.name for m in client.models.list()]
            print(f"[DEBUG] Available models: {available_models}")

            for m_name in available_models:
                clean_name = m_name.replace("models/", "")
                if "flash" in clean_name and "embed" not in clean_name and "imagen" not in clean_name:
                    model_to_use = clean_name
                    break

            if not model_to_use and available_models:
                for m_name in available_models:
                    clean_name = m_name.replace("models/", "")
                    if "embed" not in clean_name and "imagen" not in clean_name:
                        model_to_use = clean_name
                        break
        except Exception as list_err:
            print(f"[WARN] Failed to list models: {list_err}")

        if not model_to_use:
            model_to_use = "gemini-2.5-flash"

        print(f"[INFO] Dynamically selected model: {model_to_use}")

        prompt = (
            "Extract the final total paid amount from this receipt/slip. "
            "Return ONLY a JSON object: {\"amount\": 150.00}. If not found, return {\"amount\": 0.0}."
        )

        # 2. เรียกใช้งานโมเดลที่ค้นพบ
        response = client.models.generate_content(
            model=model_to_use,
            contents=[
                types.Part.from_bytes(data=contents, mime_type=mime_type),
                prompt
            ]
        )

        if not response or not response.text:
            return {"success": False, "error": "No response text received from model", "amount": 0.0}

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