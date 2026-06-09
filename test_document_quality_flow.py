from __future__ import annotations

from pathlib import Path

from bewaarhet.tools.process_test_documents import _load_expected, build_report, process_document


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
