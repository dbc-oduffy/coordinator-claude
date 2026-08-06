"""`python -m coordinator_whoami.project_rag` entry point — trampolines to the project-rag envelope CLI."""
from coordinator_whoami.project_rag.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
