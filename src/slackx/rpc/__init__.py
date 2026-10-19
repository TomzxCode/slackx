"""JSON-RPC 2.0 interface over the slackx cache and Slack operations.

The server exposes the CLI's commands as JSON-RPC methods at ``POST /rpc`` on
the same FastAPI app served by ``slackx serve``. The CLI can serve that app
with ``slackx rpc serve`` and call it with ``slackx rpc call``.
"""
