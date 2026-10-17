"""Default values for the Slack API client and the CLI.

Kept free of dependencies (in particular httpx), so a module that only needs a
constant, such as the CLI using the search limit as a command default, does not
have to load the API client to get it.
"""

DEFAULT_API_BASE = "https://slack.com/api"
DEFAULT_LIMIT = 200
DEFAULT_LIST_LIMIT = 1000
DEFAULT_SEARCH_COUNT = 20
DEFAULT_SEARCH_LIMIT = 200
DEFAULT_CHANNEL_TYPES = "public_channel,private_channel,mpim,im"
MAX_RETRIES = 5
REQUEST_TIMEOUT = 30
