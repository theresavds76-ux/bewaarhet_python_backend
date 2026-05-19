from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.classifier import classify_document
from bewaarhet.mail_client import Attachment, IncomingMail
from bewaarhet.processor import process_upload_mail
from bewaarhet.utils import detect_purpose, detect_supplier, generate_filename


ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.odt',
    '.xls', '.xlsx', '.ods', '.txt', '.csv', '.rtf',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
    '.zip',
}


def _odf_bytes(mimetype: str = 'application/vnd.oasis.opendocument.text') -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', mimetype, compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml', b'<document>safe</document>')
        archive.writestr('META-INF/manifest.xml', b'<manifest />')
    return buffer.getvalue()


def _attachment(filename: str, content: bytes) -> Attachment:
    return Attachment(
        filename=filename,
        content=content,
        content_type='application/octet-stream',
        size=len(content),
    )


def _mail(att: Attachment) -> IncomingMail:
    return IncomingMail(
        uid='recipe-1',
        from_email='user@example.com',
        subject='',
        body_text='',
        date_raw='Tue, 19 May 2026 10:00:00 +0200',
        attachments=[att],
        to_email='bewaren@bewaarhet.nl',
    )


class GeneralDocumentPurposeTests(unittest.TestCase):
    def test_odt_recipe_text_gets_recipe_pastei_filename(self) -> None:
        recipe_text = (
            'Pastei\n\n'
            '300 gram kipfilet\n'
            'tomatenblokjes\n'
            'bouillonblokjes\n'
            'aardappel\n'
            'kerrie\n'
            'masala\n'
            'madame jeanette\n'
            'Bereidingswijze: bakken en koken.'
        )
        att = _attachment('pastei.odt', _odf_bytes())

        with (
            patch('bewaarhet.classifier.settings', SimpleNamespace(openai_api_key='', openai_model='gpt-5-mini')),
            patch('bewaarhet.processor.settings', SimpleNamespace(
                allowed_extensions=ALLOWED_EXTENSIONS,
                max_attachment_mb=15,
                dropbox_base_path='/Bewaar het/Klanten',
            )),
            patch('bewaarhet.processor.ocr_space', return_value=recipe_text),
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file'),
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        send_html.assert_not_called()
        record = add_document.call_args.args[0]
        self.assertEqual(record['category'], 'overig')
        self.assertEqual(record['purpose'], 'recept')
        self.assertEqual(record['filename'], 'recept_pastei_19-05-2026.odt')

    def test_business_invoice_stays_invoice(self) -> None:
        text = 'Factuur\nFactuurnummer: 2026-001\nFactuurdatum: 19-05-2026\nTotaal EUR 42,00'
        category = classify_document(text, 'factuur.pdf', 'Factuur KPN', text[:200])
        purpose = detect_purpose(text, 'Factuur KPN', 'factuur.pdf')
        supplier = detect_supplier(text, 'Factuur KPN', 'factuur.pdf', 'noreply@kpn.com')
        filename, _date = generate_filename(category, 'factuur.pdf', text, '2026-05-19', 'Factuur KPN', supplier, purpose)

        self.assertEqual(category, 'facturen')
        self.assertEqual(purpose, 'factuur')
        self.assertTrue(filename.startswith('factuur_'))
        self.assertNotIn('recept', filename)

    def test_tax_document_stays_belasting(self) -> None:
        text = 'Belastingdienst\nBetalingsregeling\nUw betalingsregeling is goedgekeurd.'
        category = classify_document(text, 'belasting.pdf', 'Betalingsregeling belastingdienst', text[:200])
        purpose = detect_purpose(text, 'Betalingsregeling belastingdienst', 'belasting.pdf')
        supplier = detect_supplier(text, 'Betalingsregeling belastingdienst', 'belasting.pdf', 'noreply@belastingdienst.nl')
        filename, _date = generate_filename(category, 'belasting.pdf', text, '2026-05-19', '', supplier, purpose)

        self.assertEqual(category, 'belasting')
        self.assertEqual(purpose, 'betalingsregeling')
        self.assertTrue(filename.startswith('belasting_'))
        self.assertNotIn('recept', filename)

    def test_contract_stays_contract(self) -> None:
        text = 'Huurovereenkomst\nPartijen verklaren deze overeenkomst te ondertekenen.\nIngangsdatum 19-05-2026.'
        category = classify_document(text, 'contract.pdf', 'Huurovereenkomst', text[:200])
        purpose = detect_purpose(text, 'Huurovereenkomst', 'contract.pdf')
        supplier = detect_supplier(text, 'Huurovereenkomst', 'contract.pdf', 'user@example.com')
        filename, _date = generate_filename(category, 'contract.pdf', text, '2026-05-19', '', supplier, purpose)

        self.assertEqual(category, 'contracten')
        self.assertTrue(filename.startswith('contract_'))
        self.assertNotIn('recept', filename)

    def test_unknown_document_remains_neat_overig(self) -> None:
        text = 'Los document\nEnkele algemene regels zonder duidelijke administratieve context.'
        filename, _date = generate_filename('overig', 'document.txt', text, '2026-05-19', '', 'onbekend', '')

        self.assertEqual(filename, 'overig_onbekend_19-05-2026.txt')

    def test_password_note_does_not_leak_secret_value_in_filename(self) -> None:
        text = 'Wachtwoord: SuperSecret123!'
        purpose = detect_purpose(text, '', 'email_body.pdf')
        filename, _date = generate_filename('notities', 'email_body.pdf', text, '2026-05-19', '', 'onbekend', purpose)

        self.assertEqual(purpose, 'notitie')
        self.assertEqual(filename, 'notitie_wachtwoord_19-05-2026.pdf')
        self.assertNotIn('supersecret', filename)
        self.assertNotIn('123', filename)


if __name__ == '__main__':
    unittest.main()
