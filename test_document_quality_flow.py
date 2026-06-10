from __future__ import annotations

from pathlib import Path
from dataclasses import replace

import bewaarhet.classifier as classifier
from bewaarhet.classifier import classify_document_with_reason
from bewaarhet.tools.process_test_documents import (
    _load_expected,
    build_failure_review_report,
    build_report,
    is_uncertain,
    process_document,
    write_visual_review_map,
)
from bewaarhet.tools.review_document_quality import main as review_main


def test_document_quality_fixture_set_passes(tmp_path: Path) -> None:
    testdata = Path(__file__).parent / 'testdata' / 'documents'
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata) for entry in entries]
    report = build_report(results, testdata=testdata)
    report_path = tmp_path / 'document_quality_report.md'
    report_path.write_text(report, encoding='utf-8')

    assert len(results) >= 7
    assert all(result.ocr_ok for result in results)
    assert all(result.classification_ok for result in results)
    assert all(result.filename_ok for result in results)
    assert all(search['ok'] for result in results for search in result.search_results)
    assert 'Correct geclassificeerd: 7/7 (100.0%)' in report
    assert 'Zoektests geslaagd: 14/14 (100.0%)' in report


def test_real_world_document_quality_fixture_set_passes(tmp_path: Path) -> None:
    testdata = Path(__file__).parent / 'testdata' / 'real_world_documents'
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata) for entry in entries]
    report = build_report(results, testdata=testdata)
    report_path = tmp_path / 'real_world_document_quality_report.md'
    report_path.write_text(report, encoding='utf-8')

    assert len(results) >= 7
    assert all(result.ocr_ok for result in results)
    assert all(result.classification_ok for result in results)
    assert all(result.filename_ok for result in results)
    assert all(search['ok'] for result in results for search in result.search_results)
    assert 'Testset:' in report
    assert 'Correct geclassificeerd: 7/7 (100.0%)' in report
    assert 'Zoektests geslaagd: 14/14 (100.0%)' in report


def test_failure_review_report_contains_ai_decisions_and_uncertain_cases(tmp_path: Path) -> None:
    testdata = Path(__file__).parent / 'testdata' / 'real_world_documents'
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata) for entry in entries]
    report = build_failure_review_report(results, testdata=testdata)
    report_path = tmp_path / 'document_failure_review.md'
    report_path.write_text(report, encoding='utf-8')

    assert report_path.exists()
    assert '## Uncertain document bucket' in report
    assert 'lowres_health_policy' in report
    assert 'AI fallback beslissing:' in report
    assert 'OCR-preview:' in report
    assert any(is_uncertain(result) for result in results)


def test_human_review_command_writes_report(tmp_path: Path) -> None:
    testdata = Path(__file__).parent / 'testdata' / 'real_world_documents'
    report_path = tmp_path / 'document_failure_review.md'
    review_dir = tmp_path / 'review'

    exit_code = review_main(['--testdata', str(testdata), '--report', str(report_path), '--review-dir', str(review_dir)])

    assert exit_code == 0
    assert report_path.exists()
    assert (review_dir / 'index.md').exists()
    text = report_path.read_text(encoding='utf-8')
    assert 'Bewaarhet failure review' in text
    assert 'AI fallback mogelijk maar niet gebruikt:' in text


def test_visual_review_map_copies_uncertain_documents(tmp_path: Path) -> None:
    testdata = Path(__file__).parent / 'testdata' / 'real_world_documents'
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata) for entry in entries]
    review_dir = tmp_path / 'review'

    index_path = write_visual_review_map(results, output_dir=review_dir)

    assert index_path.exists()
    index_text = index_path.read_text(encoding='utf-8')
    assert 'lowres_health_policy' in index_text
    assert 'uncertain/lowres_health_policy.png' in index_text
    assert (review_dir / 'uncertain' / 'lowres_health_policy.png').exists()
    detail_path = review_dir / 'uncertain' / 'lowres_health_policy.md'
    assert detail_path.exists()
    detail_text = detail_path.read_text(encoding='utf-8')
    assert 'OCR-preview' in detail_text
    assert 'AI fallback beslissing:' in detail_text


def test_rule_based_high_confidence_skips_ai(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(classifier, 'settings', replace(classifier.settings, openai_api_key='test-key'))
    monkeypatch.setattr(classifier, 'classify_openai', lambda *args, **kwargs: calls.append(args) or 'facturen')

    result = classify_document_with_reason(
        'Factuur\nFactuurnummer F-2026-1\nFactuurdatum 09-06-2026\nTotaalbedrag EUR 10,00',
        'factuur.pdf',
        'Factuur',
        '',
        allow_ai_fallback=True,
    )

    assert result.category == 'facturen'
    assert result.method == 'rules'
    assert result.ai_fallback_enabled is True
    assert result.ai_fallback_used is False
    assert result.ai_fallback_reason == 'AI fallback skipped: rule confidence above threshold'
    assert calls == []


def test_low_confidence_can_trigger_ai_fallback_when_enabled(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(classifier, 'settings', replace(classifier.settings, openai_api_key='test-key'))
    monkeypatch.setattr(classifier, 'classify_openai', lambda *args, **kwargs: calls.append(args) or 'contracten')

    result = classify_document_with_reason(
        'Nieuwe afspraken voor samenwerking en service zonder duidelijke contractkop.',
        'afspraken.txt',
        'Afspraken',
        '',
        allow_ai_fallback=True,
    )

    assert result.category == 'contracten'
    assert result.method == 'fallback'
    assert result.ai_fallback_enabled is True
    assert result.ai_fallback_used is True
    assert calls
