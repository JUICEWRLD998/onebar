# CLAIMS

Every number in the README or post links to a row here, and each row points at a committed file.

| Claim | Value | Source file | Status |
|---|---|---|---|
| Checker rejects a planted set of 10 defective replies, 10 of 10 | 10/10 | `tests/test_checker.py` (`PLANTED`, `test_planted_control_is_exactly_ten_and_all_fail`) | verified, run `make test` |
| Template reply passes the checker on 3,360 cases (20 real forecasts x 3 times of day x with/without storm x with/without trip x 14 questions) | 3360/3360 | `tests/test_template.py` | verified, run `make test` |
