from __future__ import annotations

from io import BytesIO
import mimetypes
from pathlib import Path

import requests
from .config import settings

OCR_SPACE_MAX_UPLOAD_BYTES = 1_350_000
OCR_IMAGE_MAX_DIMENSION = 2200
OCR_IMAGE_MIN_DIMENSION = 800


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
    except ImportError as exc:
        print(f"DEBUG OCR_SPACE image_downscale_skipped=missing_pillow original_bytes={len(file_bytes)}")
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
                        print(
                            "DEBUG OCR_SPACE image_downscaled="
                            f"true original_bytes={len(file_bytes)} upload_bytes={len(candidate)} "
                            f"max_dimension={max_dimension} quality={quality}"
                        )
                        return candidate, upload_name, 'image/jpeg'
                max_dimension -= 200

            if len(best_bytes) < len(file_bytes):
                upload_name = str(Path(filename).with_suffix('.jpg'))
                print(
                    "DEBUG OCR_SPACE image_downscaled="
                    f"partial original_bytes={len(file_bytes)} upload_bytes={len(best_bytes)}"
                )
                return best_bytes, upload_name, 'image/jpeg'
    except Exception as exc:
        print(f"DEBUG OCR_SPACE image_downscale_failed={type(exc).__name__}: {exc}")

    return file_bytes, filename, mime_type


def ocr_space(file_bytes: bytes, filename: str) -> str:
    if not settings.ocr_space_api_key:
        _debug_ocr_space_empty('missing_api_key')
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
