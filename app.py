import os
from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import sqlite3
from datetime import datetime

load_dotenv()  # reads your .env file

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def init_db():
    conn = sqlite3.connect("usage.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_usage(phone_number, tokens_in, tokens_out):
    cost = (tokens_in * 0.000003) + (tokens_out * 0.000015)  # Sonnet 4.6 rates
    conn = sqlite3.connect("usage.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usage_log (phone_number, tokens_in, tokens_out, cost_usd, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (phone_number, tokens_in, tokens_out, cost, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return cost

init_db()  # runs when server starts, creates table if it doesn't exist

# stores conversation history per phone number in memory
conversation_history = {}

def chat_with_claude(phone_number, user_message):
    # get this person's history or start fresh
    if phone_number not in conversation_history:
        conversation_history[phone_number] = []

    # add their message to history
    conversation_history[phone_number].append({
        "role": "user",
        "content": user_message
    })

    # keep only last 10 messages to control costs
    if len(conversation_history[phone_number]) > 10:
        conversation_history[phone_number] = conversation_history[phone_number][-10:]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system="""You are a helpful assistant on WhatsApp. 
        Follow these rules strictly:
        - Reply in plain text only, no markdown
        - No bullet points using *, use plain dashes instead
        - No bold or italic text
        - Keep responses concise and conversational
        - If asked to write code, just write it plainly without code blocks""",
        messages=conversation_history[phone_number]
    )

    reply = response.content[0].text

    # add claude's reply to history
    conversation_history[phone_number].append({
        "role": "assistant",
        "content": reply
    })

    # log usage and cost
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    log_usage(phone_number, tokens_in, tokens_out)

    return reply

@app.route("/bot", methods=["POST"])
def bot():
    # get the incoming message details from Twilio
    incoming_msg = request.form.get("Body", "").strip()
    phone_number = request.form.get("From", "")

    # create a Twilio response object
    resp = MessagingResponse()
    msg = resp.message()

    # ignore empty messages
    if not incoming_msg:
        msg.body("Please send a text message.")
        return str(resp)

    # special command - check your own usage
    if incoming_msg.lower() == "!usage":
        conn = sqlite3.connect("usage.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(tokens_in), SUM(tokens_out), SUM(cost_usd)
            FROM usage_log WHERE phone_number = ?
        """, (phone_number,))
        result = cursor.fetchone()
        conn.close()

        if result[0]:
            msg.body(f"Your usage:\nTokens sent: {result[0]}\nTokens received: {result[1]}\nTotal cost: ${result[2]:.4f}")
        else:
            msg.body("No usage recorded yet.")
        return str(resp)

    # special command - admin sees everyone's usage
    if incoming_msg.lower() == "!all":
        conn = sqlite3.connect("usage.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT phone_number, SUM(tokens_in), SUM(tokens_out), SUM(cost_usd)
            FROM usage_log GROUP BY phone_number
        """)
        rows = cursor.fetchall()
        conn.close()

        if rows:
            report = "All usage:\n"
            for row in rows:
                report += f"\n{row[0]}\nCost: ${row[3]:.4f}\n"
            msg.body(report)
        else:
            msg.body("No usage yet.")
        return str(resp)

    # normal message - call Claude
    try:
        reply = chat_with_claude(phone_number, incoming_msg)
        msg.body(reply)
    except Exception as e:
        msg.body("Something went wrong, please try again.")
        print(f"Error: {e}")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=False, port=5000)