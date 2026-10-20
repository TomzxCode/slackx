"""JSON-RPC 2.0 interface over the slackx cache and Slack operations.

The server exposes typed methods and a ``cli.run`` passthrough as JSON-RPC
methods at ``POST /rpc`` on the same FastAPI app served by ``slackx serve``.
The CLI can serve that app with ``slackx rpc serve``, call a method with
``slackx rpc call``, forward a command with ``slackx rpc exec``, or run any
command remotely with ``slackx --remote``.
"""
