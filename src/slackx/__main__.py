"""Allow ``python -m slackx`` so the RPC server can run CLI commands in a child."""

from slackx.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
