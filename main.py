import os
import json
import re
import base64
import urllib.request
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
            return {"success": False, "error": "GEMINI_API_KEY is not set", "amount": 0.0}

        contents = await file.read()
        base64_data = base64.b64encode(contents).decode('utf-8')
        
        mime_type = file.content_type or "image/jpeg"
        if file.filename.lower().endswith(".pdf"):
            mime_type = "application/pdf"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        prompt = """
        Analyze this receipt document and extract the total paid amount (รวมทั้งสิ้น / ยอดชำระ).
        Return ONLY a JSON object format: {"amount": 40.00}
        If you cannot find any amount, return {"amount": 0.0}
        """

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
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        res_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
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
        return {"success": False, "error": str(e), "amount": 0.0}