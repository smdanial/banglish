from pathlib import Path

import pytest

from eval.textnorm import Normalizer

NORM = Normalizer.from_file(Path(__file__).resolve().parents[1] / "normalization.yaml")


@pytest.mark.parametrize("text,expected", [
    ("Amii KAL office e jabo!!", "ami kal office e jabo"),
    ("  Ammu,   ami aj raate   deri kore firbo. ", "ammu ami aj raate deri kore firbo"),
    ("Cox's Bazar e", "coxs bazar e"),
    ("৪টায় আসবো।", "4টায় আসবো"),
    ("o k, 1,500 tk", "ok 1500 taka"),
])
def test_normalize(text, expected):
    assert NORM.normalize(text) == expected


def kf(text):
    return dict(NORM.key_fields(text))


@pytest.mark.parametrize("ref,hyp", [
    ("Kal bikal 4 tay office e", "kal bikal char tay office e"),
    ("Kal bikal 4 tay", "kal bikal chartay"),
    ("Bikal sharhe 5 tay dekha", "bikal 5:30 e dekha"),
    ("Pouney 8 tay join koro", "7.45 e join koro"),
    ("Amar number 01712 345678", "amar number 01712345678"),
    ("Amar number 01712 345678", "amar number zero one seven one two three four five six seven eight"),
    ("Bashar bhara 18 hajar taka", "bashar bhara 18000 taka"),
    ("Notun phone 22 hajar 500 taka", "notun phone 22500 taka"),
    ("Aj mot 850 taka", "aj mot atsho ponchash taka"),
    ("1500 taka dao", "ponerosho taka dao"),
    ("1,500 taka", "1500 taka"),
    ("Emergency te 999", "emergency te nine nine nine"),
    ("রাত ১০টায়", "raat 10 tay"),
    ("4 tay", "4:00 tay"),
])
def test_key_fields_match(ref, hyp):
    assert kf(ref) and kf(ref) == kf(hyp)


@pytest.mark.parametrize("ref,hyp", [
    ("60 taka chailo, ami 50 taka dilam", "60 taka chailo ami 15 taka dilam"),   # wrong number
    ("60 taka chailo, ami 50 taka dilam", "60 taka chailo ami taka dilam"),      # missing number
    ("bikal 5 tay", "bikal sharhe 5 tay"),                                       # wrong time
    ("Mirpur 10 e thaki", "mirpur 10 e thaki 2 jon"),                            # extra number
])
def test_key_fields_mismatch(ref, hyp):
    assert kf(ref) != kf(hyp)


def test_no_key_fields():
    assert kf("Rahim bhai ke bolo office e aste") == {}
