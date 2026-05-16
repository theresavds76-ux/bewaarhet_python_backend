from __future__ import annotations

import requests
from .config import settings


def ocr_space(file_bytes: bytes, filename: str) -> str:
    if not settings.ocr_space_api_key:
        return ''

    try:
        response = requests.post(
            'https://api.ocr.space/parse/image',
            headers={'apikey': settings.ocr_space_api_key},
            data={
                'language': settings.ocr_space_language,
                'isOverlayRequired': 'false',
                'OCREngine': '2',
                'scale': 'false',
                'isTable': 'false',
                'detectOrientation': 'true',
            },
            files={'file': (filename, file_bytes)},
            timeout=180,
        )

        data = response.json()

        if data.get('IsErroredOnProcessing'):
            return ''

        parsed = data.get('ParsedResults') or []

        if not parsed:
            return ''

        return (parsed[0].get('ParsedText') or '').strip()

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