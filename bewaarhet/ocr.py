from __future__ import annotations

from io import BytesIO
import mimetypes
from pathlib import Path

import requests
from .config import settings

OCR_SPACE_MAX_UPLOAD_BYTES = 1_350_000
OCR_IMAGE_MAX_DIMENSION = 2200
OCR_IMAGE_MIN_DIMENSION = 800


def _prepare_image_for_ocr_upload(file_bytes: bytes, filename: str) -> tuple[bytes, str, str]:
    """Return temporary upload bytes small enough for OCR.space's free-plan limit."""
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    extension = Path(filename).suffix.lower()
    if len(file_bytes) <= OCR_SPACE_MAX_UPLOAD_BYTES:
        return file_bytes, filename, mime_type
    if extension not in {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}:
        return file_bytes, filename, mime_type

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return file_bytes, filename, mime_type

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert('RGB')
            resample_filter = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS')

            best_bytes = file_bytes
            max_dimension = OCR_IMAGE_MAX_DIMENSION
            while max_dimension >= OCR_IMAGE_MIN_DIMENSION:
                resized = image.copy()
                resized.thumbnail((max_dimension, max_dimension), resample_filter)
                for quality in (86, 82, 78, 74, 70, 66, 62, 58, 54, 50, 46):
                    buffer = BytesIO()
                    resized.save(buffer, format='JPEG', quality=quality, optimize=True, progressive=True)
                    candidate = buffer.getvalue()
                    if len(candidate) < len(best_bytes):
                        best_bytes = candidate
                    if len(candidate) <= OCR_SPACE_MAX_UPLOAD_BYTES:
                        upload_name = str(Path(filename).with_suffix('.jpg'))
                        return candidate, upload_name, 'image/jpeg'
                max_dimension -= 200

            if len(best_bytes) < len(file_bytes):
                upload_name = str(Path(filename).with_suffix('.jpg'))
                return best_bytes, upload_name, 'image/jpeg'
    except Exception:
        return file_bytes, filename, mime_type

    return file_bytes, filename, mime_type


def ocr_space(file_bytes: bytes, filename: str) -> str:
    if not settings.ocr_space_api_key:
        return ''

    try:
        upload_bytes, upload_filename, mime_type = _prepare_image_for_ocr_upload(file_bytes, filename)
        response = requests.post(
            'https://api.ocr.space/parse/image',
            headers={'apikey': settings.ocr_space_api_key},
            data={
                'language': settings.ocr_space_language,
                'isOverlayRequired': 'false',
                'OCREngine': '2',
                'scale': 'true',
                'isTable': 'false',
                'detectOrientation': 'true',
            },
            files={'file': (upload_filename, upload_bytes, mime_type)},
            timeout=180,
        )

        try:
            data = response.json()
        except ValueError:
            return ''

        if data.get('IsErroredOnProcessing'):
            return ''

        parsed = data.get('ParsedResults') or []

        if not parsed:
            return ''

        text = '\n'.join(
            (item.get('ParsedText') or '').strip()
            for item in parsed
            if isinstance(item, dict) and (item.get('ParsedText') or '').strip()
        ).strip()
        if not text:
            return ''

        return text

    except Exception:
        return ''


if __name__ == "__main__":
    test_path = "test.pdf"

    try:
        with open(test_path, "rb") as f:
            content = f.read()

        print("OCR test gestart...")

        text = ocr_space(content, test_path)

        if text:
            print("OCR gelukt:")
            print("-" * 40)
            print(text[:1000])
        else:
            print("Geen OCR tekst gevonden.")

    except FileNotFoundError:
        print("Plaats een bestand genaamd test.pdf in de hoofdmap van het project.")
