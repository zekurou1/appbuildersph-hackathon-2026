"""Create synthetic originals for Android PDF UI validation; no private input."""
from pathlib import Path
from reportlab.pdfgen import canvas

destination = Path('reports/runtime/mobile-pdf-corpus')
destination.mkdir(parents=True, exist_ok=True)
pdf = canvas.Canvas(str(destination / 'unrelated.pdf'))
pdf.drawString(40, 750, 'Physics timetable on Wednesday.')
pdf.showPage()
pdf.drawString(40, 750, 'Rental deposit returned thirty days after moving out. Reference PDF-739.')
pdf.save()
blank = canvas.Canvas(str(destination / 'no-text.pdf'))
blank.showPage()
blank.save()
(destination / 'broken.pdf').write_bytes(b'not a PDF')
(destination / 'receipt.md').write_text('Synthetic adapter receipt. Reference TXT-812.\n', encoding='utf-8')
print(destination.resolve())
