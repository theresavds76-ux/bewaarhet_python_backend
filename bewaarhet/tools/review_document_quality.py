from __future__ import annotations

import argparse
from pathlib import Path

from bewaarhet.tools.process_test_documents import (
    DEFAULT_FAILURE_REVIEW,
    DEFAULT_REVIEW_DIR,
    DEFAULT_TESTDATA,
    _load_expected,
    build_failure_review_report,
    is_failure,
    is_uncertain,
    process_document,
    write_visual_review_map,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Maak een mensvriendelijke review van Bewaarhet documentkwaliteit.')
    parser.add_argument('--testdata', default=str(DEFAULT_TESTDATA))
    parser.add_argument('--report', default=str(DEFAULT_FAILURE_REVIEW))
    parser.add_argument('--review-dir', default=str(DEFAULT_REVIEW_DIR))
    parser.add_argument('--allow-ai-fallback', action='store_true', help='Sta echte AI fallback toe als OPENAI_API_KEY is geconfigureerd.')
    args = parser.parse_args(argv)

    testdata = Path(args.testdata).resolve()
    entries = _load_expected(testdata)
    results = [process_document(entry, testdata, allow_ai_fallback=args.allow_ai_fallback) for entry in entries]
    report = build_failure_review_report(results, testdata=testdata)
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding='utf-8')
    review_index = write_visual_review_map(results, output_dir=Path(args.review_dir).resolve())

    failures = sum(1 for result in results if is_failure(result))
    uncertain = sum(1 for result in results if not is_failure(result) and is_uncertain(result))
    print(f'Reviewed {len(results)} documents. Failures={failures}. Uncertain={uncertain}. Report: {report_path}. Visual review: {review_index}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
