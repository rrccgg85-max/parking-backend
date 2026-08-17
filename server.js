const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const cors = require('cors');
const Tesseract = require('tesseract.js');

const app = express();
app.use(cors());

const upload = multer({ storage: multer.memoryStorage() });

function parseAmountFromText(text) {
  if (!text) return 0.0;

  // จัดการช่องว่างระหว่างตัวเลข เช่น '4 0 . 0 0' -> '40.00'
  let cleaned = text.replace(/(\d)\s+(\d)/g, '$1$2');
  cleaned = cleaned.replace(/(\d)\s*\.\s*(\d)/g, '$1.$2');

  const patterns = [
    /รวมทั้งสิ้น\s*([0-9,]+(?:\.[0-9]{2})?)/i,
    /([0-9,]+(?:\.[0-9]{2})?)\s*บาท/i,
    /(?:รวม|ยอดชำระ|สุทธิ|total|amount)[\s:]*([0-9,]+(?:\.[0-9]{2})?)/i
  ];

  for (const pattern of patterns) {
    const match = cleaned.match(pattern);
    if (match && match[1]) {
      const val = parseFloat(match[1].replace(/,/g, ''));
      if (val > 0) return val;
    }
  }

  const allDecimals = cleaned.match(/(\d{1,3}(?:,\d{3})*\.\d{2})/g);
  if (allDecimals && allDecimals.length > 0) {
    const lastVal = parseFloat(allDecimals[allDecimals.length - 1].replace(/,/g, ''));
    if (lastVal > 0) return lastVal;
  }

  return 0.0;
}

app.get('/', (req, res) => {
  res.json({ status: 'online', mode: 'node_ocr_smart' });
});

app.post('/extract', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, error: 'ไม่พบไฟล์ที่อัปโหลด', amount: 0.0 });
    }

    let extractedText = '';
    const filename = req.file.originalname.toLowerCase();
    const isPdf = req.file.mimetype === 'application/pdf' || filename.endsWith('.pdf');

    if (isPdf) {
      // 1. ลองอ่านด้วย pdf-parse ก่อน (กรณีเป็น PDF ข้อความปกติ)
      try {
        const pdfData = await pdfParse(req.file.buffer);
        extractedText = pdfData.text || '';
      } catch (e) {
        console.log('pdf-parse fallback error:', e);
      }

      // 2. ถ้า pdf-parse ได้ข้อความว่างเปล่า แปลว่าเป็น PDF แบบรูปภาพ ให้ใช้ Tesseract OCR อ่านต่อทันที
      if (!extractedText.trim()) {
        console.log('PDF has no text layer, running Tesseract.js OCR...');
        try {
          const { data: { text } } = await Tesseract.recognize(
            req.file.buffer,
            'tha+eng',
            { logger: m => {} }
          );
          extractedText = text || '';
        } catch (ocrErr) {
          console.log('Tesseract OCR error:', ocrErr);
        }
      }
    } else {
      // กรณีอัปโหลดไฟล์รูปภาพโดยตรง (JPG, PNG)
      try {
        const { data: { text } } = await Tesseract.recognize(
          req.file.buffer,
          'tha+eng',
          { logger: m => {} }
        );
        extractedText = text || '';
      } catch (ocrErr) {
        console.log('Image OCR error:', ocrErr);
      }
    }

    const amount = parseAmountFromText(extractedText);

    return res.json({
      success: amount > 0,
      amount: amount,
      filename: req.file.originalname,
      raw_text: extractedText.trim().substring(0, 300)
    });

  } catch (err) {
    console.error('Extraction Error:', err);
    return res.status(500).json({ success: false, error: err.message, amount: 0.0 });
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});