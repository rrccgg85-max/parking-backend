import os
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ดึง API Key จากระบบ Render Environment Variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.get("/")
def read_root():
    return {"status": "online", "mode": "Gemini AI Vision"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        if not GEMINI_API_KEY:
            return {"success": False, "error": "GEMINI_API_KEY is not set", "amount": 0.0}

        contents = await file.read()
        
        mime_type = file.content_type
        if not mime_type or mime_type == "application/octet-stream":
            if file.filename.endswith(".pdf"):
                mime_type = "application/pdf"
            else:
                mime_type = "image/jpeg"

        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """
        Analyze this receipt document and extract the total paid amount (รวมทั้งสิ้น / ยอดชำระ).
        Return ONLY a JSON object format: {"amount": 40.00}
        If you cannot find any amount, return {"amount": 0.0}
        Do not include any formatting or markdown outside JSON.
        """

        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": contents}
        ])

        clean_res = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_res)
        extracted_amount = float(data.get("amount", 0.0))

        return {
            "success": True if extracted_amount > 0 else False,
            "amount": extracted_amount,
            "filename": file.filename
        }

    except Exception as e:
        return {"success": False, "error": str(e), "amount": 0.0}