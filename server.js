const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const cors = require('cors');

const app = express();
app.use(cors());

const upload = multer({ storage: multer.memoryStorage() });

function parseAmountFromText(text) {
  if (!text) return 0.0;

  // ทำความสะอาดข้อความ ตัดช่องว่างระหว่างตัวเลข
  let cleaned = text.replace(/(\d)\s+(\d)/g, '$1$2');
  cleaned = cleaned.replace(/(\d)\s*\.\s*(\d)/g, '$1.$2');

  // 1. ค้นหาจากคีย์เวิร์ดที่มักอยู่ใกล้กับยอดเงิน
  const patterns = [
    /รวมทั้งสิ้น\s*([0-9,]+(?:\.[0-9]{2})?)/i,
    /([0-9,]+(?:\.[0-9]{2})?)\s*บาท/i,
    /(?:รวม|ยอดชำระ|สุทธิ|จำนวนเงิน|total|amount|price)[\s:]*([0-9,]+(?:\.[0-9]{2})?)/i
  ];

  for (const pattern of patterns) {
    const match = cleaned.match(pattern);
    if (match && match[1]) {
      const val = parseFloat(match[1].replace(/,/g, ''));
      if (val > 0) return val;
    }
  }

  // 2. ถ้าไม่เจอคีย์เวิร์ด ให้ดึงตัวเลขที่มีทศนิยม .00 หรือ .xx ตัวสุดท้ายในเอกสารแทน
  const allDecimals = cleaned.match(/(\d{1,3}(?:,\d{3})*\.\d{2})/g);
  if (allDecimals && allDecimals.length > 0) {
    const lastVal = parseFloat(allDecimals[allDecimals.length - 1].replace(/,/g, ''));
    if (lastVal > 0) return lastVal;
  }

  // 3. ถ้ายังไม่เจออีก ให้หาตัวเลขจำนวนเต็มที่มีค่ามากที่สุดในเอกสาร (เผื่อเป็นยอดรวม)
  const allNumbers = cleaned.match(/\b\d{1,6}\b/g);
  if (allNumbers && allNumbers.length > 0) {
    const numbers = allNumbers.map(n => parseInt(n, 10)).filter(n => n > 0);
    if (numbers.length > 0) {
      return Math.max(...numbers);
    }
  }

  return 0.0;
}

app.get('/', (req, res) => {
  res.json({ status: 'online', mode: 'flexible_parser' });
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
    console.error('Server Error:', err);
    return res.status(500).json({ success: false, error: err.message, amount: 0.0 });
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});