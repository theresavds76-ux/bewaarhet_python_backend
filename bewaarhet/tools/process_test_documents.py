from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bewaarhet.classifier import classify_document_with_reason
from bewaarhet.search_reply import MIN_SEARCH_RESULT_SCORE, _score
from bewaarhet.utils import detect_domain, detect_purpose, detect_supplier, generate_filename


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TESTDATA = ROOT / 'testdata' / 'documents'
DEFAULT_REPORT = ROOT / 'reports' / 'document_quality_report.md'
DEFAULT_HISTORY = ROOT / 'reports' / 'document_quality_history.json'
DEFAULT_FAILURE_REVIEW = ROOT / 'reports' / 'document_failure_review.md'


@dataclass(frozen=True)
class DocumentResult:
    id: str
    path: Path
    variant: str
    expected: dict
    ocr_status: str
    ocr_text: str
    ocr_score: float
    category: str
    confidence: float
    reason: str
    method: str
    rule_confidence: float
    fallback_threshold: float
    ai_fallback_enabled: bool
    ai_fallback_used: bool
    ai_fallback_considered: bool
    ai_fallback_reason: str
    ocr_sufficient_for_ai: bool
    alternative_categories: tuple[str, ...]
    supplier: str
    purpose: str
    domain: str
    filename: str
    document_date: str
    classification_ok: bool
    supplier_ok: bool
    filename_ok: bool
    ocr_ok: bool
    search_results: list[dict]


def _load_expected(testdata: Path) -> list[dict]:
    path = testdata / 'expected.json'
    if not path.exists():
        raise FileNotFoundError(f'Expected results file not found: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    return list(data.get('documents', []))


def _load_history(history_path: Path) -> list[dict]:
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return []
    return list(data.get('runs', []))


def _append_history(history_path: Path, metrics: dict) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    runs = _load_history(history_path)
    runs.append(metrics)
    history_path.write_text(json.dumps({'runs': runs[-50:]}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _term_score(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    haystack = (text or '').lower()
    hits = sum(1 for term in terms if term.lower() in haystack)
    return round(hits / len(terms), 3)


def _ocr_text_for(document_path: Path) -> tuple[str, str]:
    sidecar = document_path.with_suffix(document_path.suffix + '.ocr.txt')
    if sidecar.exists():
        text = sidecar.read_text(encoding='utf-8')
        if len(text.strip()) < 20:
            return 'no_text_found', text
        return 'text_found', text
    if document_path.suffix.lower() == '.txt':
        text = document_path.read_text(encoding='utf-8')
        if len(text.strip()) < 20:
            return 'no_text_found', text
        return 'text_found', text
    return 'ocr_not_available_without_sidecar', ''


def _row_for_search(result: DocumentResult) -> dict[str, str]:
    return {
        'filename': result.filename,
        'supplier': result.supplier,
        'purpose': result.purpose,
        'title': result.expected.get('subject', ''),
        'original_filename': result.path.name,
        'category': result.category,
        'domain': result.domain,
        'ocr_preview': result.ocr_text[:200],
        'ocr_text': result.ocr_text,
        'dropbox_path': f"/test/{result.category}/{result.filename}",
        'year': result.document_date[:4] if result.document_date else '',
        'month': result.document_date[5:7] if len(result.document_date) >= 7 else '',
    }


def process_document(entry: dict, testdata: Path, *, allow_ai_fallback: bool = False) -> DocumentResult:
    document_path = testdata / entry['path']
    if not document_path.exists():
        raise FileNotFoundError(f"Test document not found: {document_path}")

    ocr_status, ocr_text = _ocr_text_for(document_path)
    subject = entry.get('subject', '')
    classification = classify_document_with_reason(ocr_text, document_path.name, subject, ocr_text[:500], allow_ai_fallback=allow_ai_fallback)
    supplier = detect_supplier(ocr_text, subject, document_path.name, 'test@example.com')
    purpose = detect_purpose(ocr_text, subject, document_path.name)
    domain = detect_domain(ocr_text, subject, document_path.name, supplier, purpose)
    filename, document_date = generate_filename(
        classification.category,
        document_path.name,
        ocr_text,
        entry.get('date_received', '2026-06-09'),
        subject,
        supplier=supplier,
        purpose=purpose,
    )

    expected = entry.get('expected', {})
    min_ocr_chars = int(expected.get('min_ocr_chars', 20))
    min_ocr_score = float(expected.get('min_ocr_score', 0.6))
    ocr_score = _term_score(ocr_text, expected.get('ocr_terms', []))
    expected_filename_contains = [item.lower() for item in expected.get('filename_contains', [])]
    temp_result = DocumentResult(
        id=entry['id'],
        path=document_path,
        variant=entry.get('variant', ''),
        expected=expected,
        ocr_status=ocr_status,
        ocr_text=ocr_text,
        ocr_score=ocr_score,
        category=classification.category,
        confidence=classification.confidence,
        reason=classification.reason,
        method=classification.method,
        rule_confidence=classification.rule_confidence,
        fallback_threshold=classification.fallback_threshold,
        ai_fallback_enabled=classification.ai_fallback_enabled,
        ai_fallback_used=classification.ai_fallback_used,
        ai_fallback_considered=classification.ai_fallback_considered,
        ai_fallback_reason=classification.ai_fallback_reason,
        ocr_sufficient_for_ai=classification.ocr_sufficient_for_ai,
        alternative_categories=classification.alternative_categories,
        supplier=supplier,
        purpose=purpose,
        domain=domain,
        filename=filename,
        document_date=document_date,
        classification_ok=classification.category == expected.get('category'),
        supplier_ok=(not expected.get('supplier')) or supplier == expected.get('supplier'),
        filename_ok=all(part in filename.lower() for part in expected_filename_contains),
        ocr_ok=ocr_status == 'text_found' and len(ocr_text.strip()) >= min_ocr_chars and ocr_score >= min_ocr_score,
        search_results=[],
    )
    row = _row_for_search(temp_result)
    search_results = []
    for query in expected.get('search_queries', []):
        score = _score(row, query)
        search_results.append({'query': query, 'score': score, 'ok': score >= MIN_SEARCH_RESULT_SCORE})

    return DocumentResult(**{**temp_result.__dict__, 'search_results': search_results})


def summarize_results(results: list[DocumentResult], *, testdata: Path) -> dict:
    total = len(results)
    ocr_ok = sum(1 for result in results if result.ocr_ok)
    classification_ok = sum(1 for result in results if result.classification_ok)
    search_total = sum(len(result.search_results) for result in results)
    search_ok = sum(1 for result in results for search in result.search_results if search['ok'])
    by_category: dict[str, dict] = {}
    for result in results:
        category = str(result.expected.get('category') or 'unknown')
        bucket = by_category.setdefault(category, {'total': 0, 'ocr_ok': 0, 'classification_ok': 0, 'search_total': 0, 'search_ok': 0})
        bucket['total'] += 1
        bucket['ocr_ok'] += int(result.ocr_ok)
        bucket['classification_ok'] += int(result.classification_ok)
        bucket['search_total'] += len(result.search_results)
        bucket['search_ok'] += sum(1 for search in result.search_results if search['ok'])
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'testdata': str(testdata.relative_to(ROOT)) if testdata.is_relative_to(ROOT) else str(testdata),
        'total': total,
        'ocr_ok': ocr_ok,
        'ocr_pct': round((ocr_ok / total) * 100, 1) if total else 0,
        'classification_ok': classification_ok,
        'classification_pct': round((classification_ok / total) * 100, 1) if total else 0,
        'search_ok': search_ok,
        'search_total': search_total,
        'search_pct': round((search_ok / search_total) * 100, 1) if search_total else 0,
        'avg_confidence': round(sum(result.confidence for result in results) / total, 3) if total else 0,
        'avg_ocr_score': round(sum(result.ocr_score for result in results) / total, 3) if total else 0,
        'by_expected_category': by_category,
    }


def failed_searches(result: DocumentResult) -> list[dict]:
    return [search for search in result.search_results if not search['ok']]


def low_searches(result: DocumentResult) -> list[dict]:
    return [
        search for search in result.search_results
        if search['ok'] and search['score'] < MIN_SEARCH_RESULT_SCORE + 15
    ]


def is_failure(result: DocumentResult) -> bool:
    return (
        not result.ocr_ok
        or not result.classification_ok
        or not result.filename_ok
        or bool(failed_searches(result))
    )


def uncertainty_reasons(result: DocumentResult) -> list[str]:
    reasons: list[str] = []
    if result.confidence < result.fallback_threshold:
        reasons.append(f'lage classifier confidence ({result.confidence})')
    if result.ocr_score < 0.8:
        reasons.append(f'lage OCR termscore ({result.ocr_score})')
    if low_searches(result):
        reasons.append('zoekscore laag maar net voldoende')
    if result.category == 'overig' and result.expected.get('ocr_terms'):
        reasons.append('document valt in overig terwijl herkenbare termen aanwezig zijn')
    if result.ai_fallback_considered and not result.ai_fallback_used and result.ocr_sufficient_for_ai:
        reasons.append('AI fallback had inhoudelijk gekund maar is niet gebruikt')
    return reasons


def is_uncertain(result: DocumentResult) -> bool:
    return bool(uncertainty_reasons(result))


def human_likely_category(result: DocumentResult) -> str:
    expected = result.expected.get('category')
    if expected:
        return str(expected)
    if result.category != 'overig':
        return result.category
    if result.purpose:
        return result.purpose
    return 'onzeker'


def recommendation_for(result: DocumentResult) -> str:
    if not result.ocr_ok:
        return 'OCR preprocessing verbeteren en echte OCR-output vergelijken.'
    if not result.classification_ok:
        if result.ai_fallback_considered and not result.ai_fallback_used and result.ocr_sufficient_for_ai:
            return 'AI fallback eerder inschakelen of een veilige testmock gebruiken.'
        return 'Classifier-regel verbeteren en false positive/negative toevoegen aan regressietest.'
    if result.category == 'overig' and result.confidence < result.fallback_threshold:
        return 'Overweeg subtype of AI-review, maar blijf liever veilig dan agressief fout classificeren.'
    if low_searches(result) or failed_searches(result):
        return 'Zoeksynoniemen of scoring verbeteren.'
    if not result.filename_ok:
        return 'Naamgevingsregel of testverwachting controleren.'
    return 'Geen directe actie; markeren als watchlist.'


def ocr_preview(text: str, *, limit: int = 600) -> str:
    preview = ' '.join((text or '').split())
    if len(preview) > limit:
        return preview[:limit].rstrip() + '...'
    return preview


def build_failure_review_report(results: list[DocumentResult], *, testdata: Path) -> str:
    failures = [result for result in results if is_failure(result)]
    uncertain = [result for result in results if not is_failure(result) and is_uncertain(result)]
    ai_could_have_run = [
        result for result in results
        if result.ai_fallback_considered and not result.ai_fallback_used and result.ocr_sufficient_for_ai
    ]
    by_type: dict[str, int] = {}
    for result in failures + uncertain:
        category = str(result.expected.get('category') or result.category or 'unknown')
        by_type[category] = by_type.get(category, 0) + 1

    lines = [
        '# Bewaarhet failure review',
        '',
        '## Samenvatting',
        '',
        f'- Testset: `{testdata.relative_to(ROOT) if testdata.is_relative_to(ROOT) else testdata}`',
        f'- Failures: {len(failures)}',
        f'- Uncertain cases: {len(uncertain)}',
        f'- AI fallback mogelijk maar niet gebruikt: {len(ai_could_have_run)}',
        '',
        '## Documenttypes met meeste aandacht',
        '',
    ]
    if by_type:
        for category, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
            lines.append(f'- {category}: {count}')
    else:
        lines.append('- Geen failures of onzekerheden in deze run.')

    def add_section(title: str, items: list[DocumentResult]) -> None:
        lines.extend(['', f'## {title}', ''])
        if not items:
            lines.append('Geen documenten in deze bucket.')
            return
        for result in items:
            failed_queries = ', '.join(f"{item['query']} ({item['score']})" for item in failed_searches(result)) or 'geen'
            low_queries = ', '.join(f"{item['query']} ({item['score']})" for item in low_searches(result)) or 'geen'
            reasons = '; '.join(uncertainty_reasons(result)) or 'harde failure'
            variant = result.variant or result.expected.get('variant') or result.expected.get('document_variant') or result.expected.get('source_variant') or 'niet gespecificeerd'
            lines.extend([
                f'### {result.id}',
                '',
                f'- Bestand: `{result.path.relative_to(ROOT)}`',
                f'- Documentvariant: {variant}',
                f"- Verwachte categorie: {result.expected.get('category')}",
                f'- Voorspelde categorie: {result.category}',
                f'- Confidence: {result.confidence}',
                f'- Rule-based confidence: {result.rule_confidence}',
                f'- Fallback threshold: {result.fallback_threshold}',
                f'- OCR-status: {result.ocr_status}',
                f'- OCR-score: {result.ocr_score}',
                f'- OCR-preview: {ocr_preview(result.ocr_text)}',
                f'- Zoekvragen gefaald: {failed_queries}',
                f'- Zoekvragen laag maar geslaagd: {low_queries}',
                f'- Classifier-route: {result.method}',
                f'- Classifier reason: {result.reason}',
                f'- Alternatieve categorieen: {", ".join(result.alternative_categories) or "geen"}',
                f'- AI fallback enabled: {result.ai_fallback_enabled}',
                f'- AI fallback used: {result.ai_fallback_used}',
                f'- AI fallback considered: {result.ai_fallback_considered}',
                f'- AI fallback beslissing: {result.ai_fallback_reason}',
                f'- OCR zinvol voor AI: {result.ocr_sufficient_for_ai}',
                f'- Mens zou waarschijnlijk herkennen als: {human_likely_category(result)}',
                f'- Reviewreden: {reasons}',
                f'- Aanbeveling: {recommendation_for(result)}',
                '',
            ])

    add_section('Failures', failures)
    add_section('Uncertain document bucket', uncertain)
    return '\n'.join(lines) + '\n'


def build_report(results: list[DocumentResult], *, testdata: Path, history: list[dict] | None = None) -> str:
    metrics = summarize_results(results, testdata=testdata)
    previous = history[-1] if history else None
    total = len(results)
    uncertain = [result for result in results if is_uncertain(result)]
    wrong = [result for result in results if not result.classification_ok]
    ai_could_have_run = [
        result for result in results
        if result.ai_fallback_considered and not result.ai_fallback_used and result.ocr_sufficient_for_ai
    ]

    lines = [
        '# Bewaarhet document quality report',
        '',
        '## Samenvatting',
        '',
        f"- Testset: `{metrics['testdata']}`",
        f'- Totaal aantal documenten: {total}',
        f"- OCR bruikbaar: {metrics['ocr_ok']}/{total} ({metrics['ocr_pct']}%)",
        f"- Gemiddelde OCR termscore: {metrics['avg_ocr_score']}",
        f"- Correct geclassificeerd: {metrics['classification_ok']}/{total} ({metrics['classification_pct']}%)",
        f'- Uncertain cases: {len(uncertain)}',
        f'- Fout geclassificeerd: {len(wrong)}',
        f'- AI fallback mogelijk maar niet gebruikt: {len(ai_could_have_run)}',
        f"- Zoektests geslaagd: {metrics['search_ok']}/{metrics['search_total']} ({metrics['search_pct']}%)",
        f"- Gemiddelde classificatieconfidence: {metrics['avg_confidence']}",
        '',
        '## Trends',
        '',
    ]
    if previous:
        lines.extend([
            f"- Vorige run OCR: {previous.get('ocr_pct')}% -> huidige run: {metrics['ocr_pct']}%",
            f"- Vorige run classificatie: {previous.get('classification_pct')}% -> huidige run: {metrics['classification_pct']}%",
            f"- Vorige run zoekscore: {previous.get('search_pct')}% -> huidige run: {metrics['search_pct']}%",
            f"- Vorige run documenten: {previous.get('total')} -> huidige run documenten: {metrics['total']}",
        ])
    else:
        lines.append('- Nog geen eerdere run in history.')

    lines.extend(['', '## Performance per documenttype', ''])
    for category, bucket in sorted(metrics['by_expected_category'].items()):
        lines.append(
            f"- {category}: OCR {bucket['ocr_ok']}/{bucket['total']}, "
            f"classificatie {bucket['classification_ok']}/{bucket['total']}, "
            f"zoektests {bucket['search_ok']}/{bucket['search_total']}"
        )

    lines.extend(['', '## Details', ''])
    for result in results:
        search_summary = ', '.join(f"{item['query']}={item['score']}{' ok' if item['ok'] else ' fail'}" for item in result.search_results)
        lines.extend([
            f'### {result.id}',
            '',
            f'- Bestand: `{result.path.relative_to(ROOT)}`',
            f'- OCR: {result.ocr_status}, chars={len(result.ocr_text.strip())}, termscore={result.ocr_score}, ok={result.ocr_ok}',
            f"- Verwacht type: {result.expected.get('category')}",
            f'- Gevonden type: {result.category}, confidence={result.confidence}',
            f'- Reden: {result.reason}',
            f'- Classifier-route: {result.method}',
            f'- Rule confidence/fallback threshold: {result.rule_confidence}/{result.fallback_threshold}',
            f'- AI fallback: enabled={result.ai_fallback_enabled}, considered={result.ai_fallback_considered}, used={result.ai_fallback_used}',
            f'- AI fallback beslissing: {result.ai_fallback_reason}',
            f'- Partij: {result.supplier} (ok={result.supplier_ok})',
            f'- Purpose/domain: {result.purpose}/{result.domain}',
            f'- Bestandsnaam: `{result.filename}` (ok={result.filename_ok})',
            f"- Zoektests: {search_summary or 'geen'}",
            '',
        ])

    improvements: list[str] = []
    for result in results:
        if not result.ocr_ok:
            improvements.append(f'{result.id}: OCR levert onvoldoende tekst/termscore op.')
        if not result.classification_ok:
            improvements.append(f"{result.id}: verwacht {result.expected.get('category')}, kreeg {result.category}.")
        if result.confidence < 0.65:
            improvements.append(f'{result.id}: lage confidence ({result.confidence}); reden: {result.reason}.')
        for reason in uncertainty_reasons(result):
            if 'lage classifier confidence' not in reason:
                improvements.append(f'{result.id}: onzekerheid - {reason}.')
        for search in result.search_results:
            if not search['ok']:
                improvements.append(f"{result.id}: zoekterm '{search['query']}' scoort te laag ({search['score']}).")

    lines.extend(['## Top verbeterpunten', ''])
    if improvements:
        for index, item in enumerate(improvements[:10], start=1):
            lines.append(f'{index}. {item}')
    else:
        lines.append('Geen blokkerende verbeterpunten in deze testset.')
    lines.append('')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verwerk lokale Bewaarhet testdocumenten zonder mail, Dropbox of billing.')
    parser.add_argument('--testdata', default=str(DEFAULT_TESTDATA))
    parser.add_argument('--report', default=str(DEFAULT_REPORT))
    parser.add_argument('--history', default=str(DEFAULT_HISTORY))
    parser.add_argument('--failure-review', default=str(DEFAULT_FAILURE_REVIEW))
    parser.add_argument('--allow-ai-fallback', action='store_true', help='Sta echte AI fallback toe als OPENAI_API_KEY is geconfigureerd.')
    args = parser.parse_args(argv)

    testdata = Path(args.testdata).resolve()
    report_path = Path(args.report).resolve()
    history_path = Path(args.history).resolve()
    history = _load_history(history_path)
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata, allow_ai_fallback=args.allow_ai_fallback) for entry in entries]
    report = build_report(results, testdata=testdata, history=history)
    failure_review = build_failure_review_report(results, testdata=testdata)
    _append_history(history_path, summarize_results(results, testdata=testdata))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding='utf-8')
    failure_review_path = Path(args.failure_review).resolve()
    failure_review_path.parent.mkdir(parents=True, exist_ok=True)
    failure_review_path.write_text(failure_review, encoding='utf-8')
    print(f'Processed {len(results)} documents. Report: {report_path}')
    print(f'Failure review: {failure_review_path}')
    failed = [
        result for result in results
        if not result.ocr_ok
        or not result.classification_ok
        or not result.filename_ok
        or any(not search['ok'] for search in result.search_results)
    ]
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
