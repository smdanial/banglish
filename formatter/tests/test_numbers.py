import pytest

from banglish_formatter.numbers import find_numbers
from banglish_formatter.text import tokenize
from banglish_formatter.vocab import get_vocab


def values(text):
    return [s.value for s in find_numbers(tokenize(text), get_vocab())]


@pytest.mark.parametrize("text,expected", [
    ("50", [50]),
    ("pochash", [50]),
    ("pachash", [50]),
    ("dui hajar", [2000]),
    ("dui hajar pach sho", [2500]),
    ("ek hajar dosh", [1010]),
    ("1 hajar 200", [1200]),
    ("pachsho", [500]),
    ("dusho", [200]),
    ("der sho", [150]),
    ("arai hajar", [2500]),
    ("sharey tin hajar", [3500]),
    ("sharey 4", [4.5]),
    ("paune 5", [4.75]),
    ("soa 4", [4.25]),
    ("50 60", [50, 60]),
    ("1,200", [1200]),
    ("2k", [2000]),
    ("৫০", [50]),
    ("ek lakh", [100000]),
])
def test_number_values(text, expected):
    assert values(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("meeting at 5", [5]),        # English "at" is not 8
    ("at taka", [8]),             # but "at taka" is 8 taka
    ("eta noy", []),              # "noy" = "is not"
    ("noy tay", [9]),
    ("der", []),                  # fraction word alone is not a number
    ("sharey", []),
])
def test_ambiguous_words(text, expected):
    assert values(text) == expected
