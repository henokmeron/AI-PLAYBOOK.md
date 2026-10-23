"""Allow integrations.verify_mailbox to be run as: python3 -m integrations.verify_mailbox"""
from .verify_mailbox import main
import sys

if __name__ == "__main__":
    sys.exit(main())
