"""`python -m coordinator_whoami.session` entry point — trampolines to the session envelope CLI."""
from coordinator_whoami.session.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
