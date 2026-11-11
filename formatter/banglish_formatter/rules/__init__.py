"""Rules are tried in order; each returns a Candidate or None. The most confident one wins."""
from .expenses import expenses_rule
from .schedule import schedule_rule

RULES = [schedule_rule, expenses_rule]
