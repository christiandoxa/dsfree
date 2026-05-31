# dsfree

Minimal Python client for the current `chat.deepseek.com` web chat endpoints.

This project is unofficial and depends on private web behavior. It can stop
working when DeepSeek changes the site, authentication, proof-of-work flow, or
stream format.

## Install

Use Python 3.10 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Authentication

Preferred: let the CLI ask for the token. Input is hidden and does not enter
shell history.

```bash
python dsfree.py
```

Do not commit tokens, cookies, or generated credential files.

## Quick Test

```bash
python example.py
```

## CLI

Start an interactive chat:

```bash
python dsfree.py
```

Send one prompt and exit without putting the token in shell history:

```bash
printf 'Reply only with: pong' | python dsfree.py
```

Argument and environment modes are still supported:

```bash
python dsfree.py <token> "Reply only with: pong"
DEEPSEEK_AUTH_TOKEN='your-token' python dsfree.py
```

## Minimal Usage

```python
from dsk.api import DeepSeekAPI

api = DeepSeekAPI("your-token")
chat_id = api.create_chat_session()

for chunk in api.chat_completion(
    chat_id,
    "Reply only with: pong",
    thinking_enabled=False,
    search_enabled=False,
):
    if chunk["type"] == "text":
        print(chunk["content"], end="", flush=True)
```

## Notes

- Streaming responses are parsed from DeepSeek's current patch-style event
  stream.
- `thinking_enabled=True` returns thinking chunks when the web endpoint emits
  them.
- `search_enabled=True` asks the web endpoint to use search when available.
- Cloudflare or AWS WAF challenges may require a fresh browser session.

## Security

Keep credentials outside the repository. Safest local-only pattern:

```bash
python dsfree.py
```
