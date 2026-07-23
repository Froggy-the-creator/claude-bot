# WhatsApp AI Assistant

A WhatsApp chatbot backed by the Anthropic API. Messages arrive via a Twilio webhook, get answered by Claude with per-user conversation context, and every call is logged to SQLite with a token and cost breakdown.

Built to learn webhook-driven architecture, third-party API integration, and deployment of a live service.

## How it works

```
WhatsApp user  ->  Twilio  ->  POST /bot  ->  Flask  ->  Anthropic API
                                               |
                                               v
                                          usage.db (tokens, cost)
```

Twilio receives the WhatsApp message and forwards it to the `/bot` endpoint as a form POST. Flask pulls out the sender and message body, appends it to that sender's conversation history, and sends the thread to Claude. The reply goes back as TwiML, which Twilio delivers to WhatsApp.

Each exchange is written to a local SQLite database with input tokens, output tokens, and computed cost, so usage is auditable per phone number.

## Security

- **Webhook authentication.** Every request to `/bot` must carry a valid `X-Twilio-Signature`, verified against the account auth token. Unsigned or forged requests are rejected with 403, so the endpoint cannot be used to spend API credits by anyone who discovers the URL.
- **Admin authorisation.** The `!all` command exposes other users' phone numbers, so it is gated on an allow-list. Callers who are not on it get an "Unknown command" reply rather than an explicit denial, to avoid confirming that the command exists.
- **Secrets** are read from environment variables only; `.env` and the usage database are gitignored.

## Features

- **Per-user conversation context** — history is kept separately for each phone number, trimmed to the last 10 messages to bound token spend.
- **Usage and cost logging** — every API call records tokens in/out and a computed USD cost to SQLite.
- **`!usage` command** — replies with the sender's own cumulative tokens and cost.
- **`!all` command** — aggregate usage across all users, restricted to an admin allow-list.
- **Plain-text output** — the system prompt suppresses markdown, since WhatsApp renders it poorly.

## Requirements

- Python 3.10+
- An Anthropic API key
- A Twilio account with the WhatsApp sandbox enabled

## Setup

Clone and install dependencies:

```bash
git clone https://github.com/Froggy-the-creator/<repo-name>.git
cd <repo-name>
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
TWILIO_AUTH_TOKEN=your-twilio-auth-token
ADMIN_NUMBERS=whatsapp:+6500000000
```

`TWILIO_AUTH_TOKEN` is in the Twilio console under Account Info. `ADMIN_NUMBERS` is optional; leave it empty and the `!all` command is simply unavailable to everyone.

Run locally:

```bash
python app.py
```

The app listens on port 5000. To let Twilio reach it during development, expose it with a tunnel:

```bash
ngrok http 5000
```

Then in the Twilio console, set the WhatsApp sandbox webhook ("when a message comes in") to:

```
https://<your-ngrok-subdomain>.ngrok.io/bot
```

Send a message to the sandbox number from WhatsApp to test.

## Deployment

The included `Procfile` runs the app under gunicorn:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

Set `ANTHROPIC_API_KEY` as an environment variable in your hosting platform rather than committing a `.env` file. After deploying, update the Twilio webhook URL to point at your deployed `/bot` endpoint.

Note that on platforms with an ephemeral filesystem, `usage.db` is reset on every redeploy. Point SQLite at a mounted volume, or swap to a managed database, if the usage log needs to persist.

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Authenticates calls to the Anthropic API |
| `TWILIO_AUTH_TOKEN` | Yes | Verifies that incoming webhooks genuinely came from Twilio |
| `ADMIN_NUMBERS` | No | Comma-separated numbers permitted to run `!all` |

Model choice, `max_tokens`, the history window, and the cost-per-token rates are set at the top of `app.py`. The rates are hardcoded to match the model in use — update both together if you switch models.

## Known limitations

These are understood tradeoffs rather than oversights, and are the next things to address:

- **Conversation history is in-process memory.** It is lost on restart, and under a multi-worker gunicorn setup each worker keeps its own copy, so context can be inconsistent. Moving history into SQLite would resolve both.
- **No rate limiting**, so a single user can drive up cost without bound.
- **WhatsApp caps messages at 1600 characters**; longer replies from Claude will fail to send.

## Project structure

```
.
├── app.py             # Flask app, webhook handler, Claude integration, usage logging
├── requirements.txt   # Pinned dependencies
├── Procfile           # Process definition for deployment
├── .gitignore
└── README.md
```

## License

MIT
