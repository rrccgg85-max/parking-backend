const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const cors = require('cors');

const app = express();
app.use(cors());

const upload = multer({ storage: multer.memoryStorage() });

function parseAmountFromText(text) {
  if (!text) return 0.0;

  // รวมช่องว่างที่หลุดมาจาก PDF เช่น '4 0 . 0 0' -> '40.00'
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
  res.json({ status: 'online', mode: 'node_pdf_parse' });
});

app.post('/extract', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, error: 'ไม่พบไฟล์ที่อัปโหลด', amount: 0.0 });
    }

    let extractedText = '';

    if (req.file.mimetype === 'application/pdf' || req.file.originalname.toLowerCase().endsWith('.pdf')) {
      const pdfData = await pdfParse(req.file.buffer);
      extractedText = pdfData.text || '';
    } else {
      return res.status(400).json({ success: false, error: 'รองรับเฉพาะไฟล์ PDF', amount: 0.0 });
    }

    const amount = parseAmountFromText(extractedText);

    return res.json({
      success: amount > 0,
      amount: amount,
      filename: req.file.originalname,
      raw_text: extractedText.trim().substring(0, 300)
    });

  } catch (err) {
    return res.status(500).json({ success: false, error: err.message, amount: 0.0 });
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});