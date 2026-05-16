from __future__ import annotations

import mimetypes

import requests
from .config import settings


def _debug_ocr_space_empty(reason: str, response=None, data=None, exc: Exception | None = None) -> None:
    print(f"DEBUG OCR_SPACE empty_reason={reason}")
    if response is not None:
        print(f"DEBUG OCR_SPACE status_code={response.status_code}")
        raw_response = (response.text or '').replace('\r', ' ').replace('\n', ' ')
        print(f"DEBUG OCR_SPACE raw_response={raw_response[:4000]}")
    if data is not None:
        parsed = data.get('ParsedResults')
        print(f"DEBUG OCR_SPACE IsErroredOnProcessing={data.get('IsErroredOnProcessing')}")
        print(f"DEBUG OCR_SPACE ParsedResults_present={bool(parsed)}")
        if isinstance(parsed, list):
            parsed_text_length = sum(len((item or {}).get('ParsedText') or '') for item in parsed)
            print(f"DEBUG OCR_SPACE ParsedText_length={parsed_text_length}")
        if data.get('ErrorMessage'):
            print(f"DEBUG OCR_SPACE ErrorMessage={data.get('ErrorMessage')}")
        if data.get('ErrorDetails'):
            print(f"DEBUG OCR_SPACE ErrorDetails={data.get('ErrorDetails')}")
    if exc is not None:
        print(f"DEBUG OCR_SPACE exception={type(exc).__name__}: {exc}")


def ocr_space(file_bytes: bytes, filename: str) -> str:
    if not settings.ocr_space_api_key:
        _debug_ocr_space_empty('missing_api_key')
        return ''

    try:
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
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
            files={'file': (filename, file_bytes, mime_type)},
            timeout=180,
        )

        try:
            data = response.json()
        except ValueError as exc:
            _debug_ocr_space_empty('invalid_json_response', response=response, exc=exc)
            return ''

        if data.get('IsErroredOnProcessing'):
            _debug_ocr_space_empty('api_error', response=response, data=data)
            return ''

        parsed = data.get('ParsedResults') or []

        if not parsed:
            _debug_ocr_space_empty('missing_parsed_results', response=response, data=data)
            return ''

        text = '\n'.join(
            (item.get('ParsedText') or '').strip()
            for item in parsed
            if isinstance(item, dict) and (item.get('ParsedText') or '').strip()
        ).strip()
        if not text:
            _debug_ocr_space_empty('empty_parsed_text', response=response, data=data)
            return ''

        return text

    except Exception as exc:
        _debug_ocr_space_empty('request_exception', exc=exc)
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
