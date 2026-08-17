import os
import json
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
    return {"status": "online", "mode": "Gemini AI Vision"}

@app.post("/extract")
async def extract_amount(file: UploadFile = File(...)):
    try:
        if not GEMINI_API_KEY:
            return {"success": False, "error": "GEMINI_API_KEY is not set", "amount": 0.0}

        contents = await file.read()
        
        mime_type = file.content_type
        if not mime_type or mime_type == "application/octet-stream":
            if file.filename.lower().endswith(".pdf"):
                mime_type = "application/pdf"
            else:
                mime_type = "image/jpeg"

        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = """
        Analyze this receipt document and extract the total paid amount (รวมทั้งสิ้น / ยอดชำระ).
        Return ONLY a JSON object format: {"amount": 40.00}
        If you cannot find any amount, return {"amount": 0.0}
        Do not include any formatting or markdown outside JSON.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=contents,
                    mime_type=mime_type,
                ),
                prompt,
            ]
        )

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