from .classifier import classify_rules


def test_examples():
    assert classify_rules('Factuurdatum en factuurnummer IBAN') == 'facturen'
    assert classify_rules('Bedankt voor uw bezoek totaal pinbon') == 'bonnen'
    assert classify_rules('Belastingdienst voorlopige aanslag inkomstenbelasting') == 'belasting'
    assert classify_rules('Huurovereenkomst looptijd handtekening') == 'contracten'
