import os
import json
import re
import base64
import urllib.request
import urllib.error
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

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
    return {"status": "online", "mode": "Direct REST API"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        if not GEMINI_API_KEY:
            print("Error: GEMINI_API_KEY is not set")
            return {"success": False, "error": "GEMINI_API_KEY is not set", "amount": 0.0}

        contents = await file.read()
        if not contents:
            return {"success": False, "error": "Uploaded file is empty", "amount": 0.0}

        base64_data = base64.b64encode(contents).decode('utf-8')
        
        filename_lower = file.filename.lower()
        if filename_lower.endswith(".pdf"):
            mime_type = "application/pdf"
        elif filename_lower.endswith(".png"):
            mime_type = "image/png"
        elif filename_lower.endswith(".webp"):
            mime_type = "image/webp"
        elif filename_lower.endswith(".heic"):
            mime_type = "image/heic"
        else:
            mime_type = file.content_type or "image/jpeg"

        print(f"Processing file: {file.filename} with mime_type: {mime_type}")

        # **เปลี่ยนเป็น gemini-1.5-flash**
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        prompt = (
            "Analyze this receipt or slip image carefully and extract the final total paid amount "
            "(เช่น จำนวนเงิน, ยอดชำระ, รวมทั้งสิ้น, Net Total, Grand Total).\n"
            "Respond ONLY with a valid JSON object matching this exact format: {\"amount\": 150.00}.\n"
            "If no amount can be extracted or found, return {\"amount\": 0.0}."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as http_err:
            err_msg = http_err.read().decode('utf-8')
            print(f"Gemini API HTTP Error: {err_msg}")
            return {"success": False, "error": f"API Error: {http_err.code}", "amount": 0.0}

        candidates = res_data.get('candidates', [])
        if not candidates:
            return {"success": False, "error": "No response candidate from Gemini", "amount": 0.0}

        res_text = candidates[0]['content']['parts'][0]['text'].strip()
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