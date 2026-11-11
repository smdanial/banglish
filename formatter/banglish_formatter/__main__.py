"""Try it: python -m banglish_formatter "akash er sathe meeting ache bikal 4 tay" """
import json
import sys

from . import format_note

if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    print(json.dumps(format_note(text), ensure_ascii=False, indent=2))
