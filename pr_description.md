🎯 **What:** The code health issue addressed
Replaced the usage of `print()` with `logger.error()` for exception and error handling within `managers/tag_manager.py`. Removed unneeded trailing spaces in the file as well.

💡 **Why:** How this improves maintainability
Logging errors properly using the `logging` module guarantees that application errors are correctly recorded without polluting standard output streams, which is cleaner and safer for production environments. It also consolidates log formatting.

✅ **Verification:** How you confirmed the change is safe
- Setup virtual environment with `pytest`, `pytest-qt`, and `flake8`.
- Ran `pytest tests/test_tag_manager.py` verifying all tags tests still succeed.
- Ran `pytest tests/` achieving a 100% test pass rate across the entirety of 41 tests.
- Linted the changed file with `flake8 --ignore=E501,E221,E203,F401,W503` making sure no new style issues were introduced.

✨ **Result:** The improvement achieved
A more consistent and robust logging strategy in the TagManager handling errors correctly.
