from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.cleanup_missing_files import main


class CleanupMissingFilesTests(unittest.TestCase):
    def test_marks_missing_paths_and_prints_summary(self) -> None:
        rows = [
            {'id': 1, 'dropbox_path': '/valid.pdf'},
            {'id': 2, 'dropbox_path': '/missing.pdf'},
        ]

        def path_exists(path: str) -> bool:
            return path == '/valid.pdf'

        output = StringIO()
        with (
            patch('bewaarhet.cleanup_missing_files.init_db'),
            patch('bewaarhet.cleanup_missing_files.all_documents', return_value=rows),
            patch('bewaarhet.cleanup_missing_files.path_exists', side_effect=path_exists),
            patch('bewaarhet.cleanup_missing_files.mark_missing_file') as mark_missing_file,
            redirect_stdout(output),
        ):
            main()

        mark_missing_file.assert_called_once_with(2)
        self.assertIn('checked: 2', output.getvalue())
        self.assertIn('missing: 1', output.getvalue())
        self.assertIn('valid: 1', output.getvalue())


if __name__ == '__main__':
    unittest.main()
