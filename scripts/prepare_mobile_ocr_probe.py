"""Create consent-free screenshot text fixtures for the Android OCR journey."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

destination = Path('reports/runtime/mobile-ocr-corpus')
destination.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (1280, 720), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 42)
draw.text((60, 70), 'Rental deposit returned after moving out.', fill='black', font=font)
draw.text((60, 160), 'Reference PKG-483', fill='black', font=font)
draw.text((60, 250), 'Physics laboratory on Wednesday.', fill='black', font=font)
image.save(destination / 'unrelated.png')
image.save(destination / 'receipt.jpg', quality=95)
Image.new('RGB', (1280, 720), 'white').save(destination / 'blank.png')
(destination / 'broken.png').write_bytes(b'not an image')
(destination / 'note.md').write_text('Synthetic adapter receipt. Reference TXT-812.\n', encoding='utf-8')
print(destination.resolve())
