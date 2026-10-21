"""Allow ``python -m rapidgrab``."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
