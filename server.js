const express = require('express');
const multer = require('multer');
const { PDFDocument } = require('pdf-lib');
const cors = require('cors');
const Tesseract = require('tesseract.js');
const { pdf } = require('pdf-to-img');

const app = express();
const upload = multer({ storage: multer.memoryStorage() });

app.use(cors());
app.use(express.json({ limit: '50mb' }));
// เพิ่มโค้ดนี้ไว้ก่อนส่วน app.listen หรือใต้ app.use(cors());
app.get('/', (req, res) => {
  res.json({ status: 'online', message: 'Parking Backend is running successfully!' });
});

// API ประมวลผล PDF & OCR ใบเสร็จ
app.post('/api/process-receipts', upload.array('files'), async (req, res) => {
    try {
        const files = req.files;
        if (!files || files.length === 0) {
            return res.status(400).json({ success: false, message: 'กรุณาเลือกไฟล์ PDF' });
        }

        const results = [];
        const mergedPdf = await PDFDocument.create();

        for (const file of files) {
            // 1. รวม PDF
            try {
                const pdfDoc = await PDFDocument.load(file.buffer);
                const copiedPages = await mergedPdf.copyPages(pdfDoc, pdfDoc.getPageIndices());
                copiedPages.forEach(page => mergedPdf.addPage(page));
            } catch (e) {
                console.log(`ไม่สามารถอ่านไฟล์ ${file.originalname} ได้`);
            }

            // 2. OCR อ่านยอดเงินจากใบเสร็จ
            let amount = 0;
            try {
                const document = await pdf(file.buffer, { scale: 2 });
                let firstPageImg = null;
                for await (const page of document) {
                    firstPageImg = page;
                    break;
                }

                if (firstPageImg) {
                    const { data: { text } } = await Tesseract.recognize(firstPageImg, 'tha+eng');
                    
                    // ดึงตัวเลขยอดเงินด้วย Regex
                    const matches = text.match(/(?:รวม|ชำระ|สุทธิ|จำนวนเงิน|ค่าจอด|ยอด|TOTAL|AMOUNT|NET|บาท|BAHT|THB)\D{0,15}(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+)/gi);
                    if (matches && matches.length > 0) {
                        const num = matches[matches.length - 1].match(/(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+)/);
                        if (num) amount = parseFloat(num[0].replace(/,/g, ''));
                    } else {
                        const decimals = text.match(/\b\d{1,4}\.\d{2}\b/g);
                        if (decimals && decimals.length > 0) amount = parseFloat(decimals[decimals.length - 1]);
                    }
                }
            } catch (ocrErr) {
                console.log(`⚠️ OCR อ่านไฟล์ ${file.originalname} ไม่สำเร็จ:`, ocrErr.message);
            }

            results.push({ 
                id: Date.now() + Math.random().toString(36).substring(2, 5), // Unique ID
                fileName: file.originalname, 
                amount: amount,
                date: new Date().toLocaleDateString('th-TH')
            });
        }

        const pdfBytes = await mergedPdf.save();
        const base64Pdf = Buffer.from(pdfBytes).toString('base64');

        res.json({ success: true, items: results, newPdfBase64: base64Pdf });

    } catch (error) {
        console.error("Server Error:", error);
        res.status(500).json({ success: false, message: error.message });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 Server พร้อมทำงานที่ http://localhost:${PORT}`));