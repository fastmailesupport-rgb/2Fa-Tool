
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import re
import html
import os
import secrets
import string
import csv
import io

app = Flask(__name__)
CORS(app)

# ==========================================
# USERNAME & PASSWORD GENERATOR CONFIGURATION
# ==========================================

ALPHANUM = string.ascii_letters + string.digits


def generate_random_value(length):
    return ''.join(secrets.choice(ALPHANUM) for _ in range(length))


# ==========================================
# EXISTING MICROSOFT TOKEN SYSTEM
# ==========================================

def get_access_token(refresh_token, client_id):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/.default"
    }

    try:
        res = requests.post(token_url, data=payload)

        if res.status_code == 200:
            return res.json().get("access_token")

    except Exception as e:
        print("Token generation error:", str(e))

    return None


# ==========================================
# EXISTING OTP READER
# ==========================================

@app.route('/get-otp', methods=['POST'])
def get_otp():
    try:
        data = request.json
        raw_input = data.get('token', '').strip()

        if not raw_input:
            return jsonify({"error": "Token is missing"}), 400

        extracted_email = "Unknown"
        access_token = None

        if '|' in raw_input:
            parts = [p.strip() for p in raw_input.split('|')]

            if len(parts) >= 4:
                extracted_email = parts[0]
                refresh_token = parts[2]
                client_id = parts[3]
                access_token = get_access_token(refresh_token, client_id)

            elif len(parts) == 2:
                access_token = get_access_token(parts[0], parts[1])

        if not access_token:
            access_token = raw_input

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        graph_url = (
            'https://graph.microsoft.com/v1.0/me/messages'
            '?$top=15&$orderby=receivedDateTime desc'
        )

        response = requests.get(
            graph_url,
            headers=headers
        )

        if response.status_code != 200:
            return jsonify({
                "error": "Invalid or expired token",
                "details": response.text
            }), 401

        messages_data = response.json().get('value', [])

        if not messages_data:
            return jsonify({
                "email": extracted_email,
                "sender": "No Messages",
                "subject": "Inbox is empty",
                "otp": "------",
                "full_message": "No recent messages found in this inbox.",
                "messages_list": []
            })

        formatted_messages = []
        latest_otp = "------"
        target_msg = messages_data[0]

        for idx, msg in enumerate(messages_data):

            sender_email = msg.get(
                'from', {}
            ).get(
                'emailAddress', {}
            ).get('address', 'Unknown')

            sender_name = msg.get(
                'from', {}
            ).get(
                'emailAddress', {}
            ).get('name', sender_email)

            subject = msg.get('subject', 'No Subject')
            received_time = msg.get('receivedDateTime', '')

            body_content = msg.get(
                'body', {}
            ).get('content', '')

            clean_text = re.sub(
                '<[^<]+?>', ' ', body_content
            )

            clean_text = html.unescape(clean_text)
            clean_text = re.sub(
                r'\s+', ' ', clean_text
            ).strip()

            msg_otp = "N/A"

            sub_match = re.search(
                r'\b([0-9]{4,8})\b', subject
            )

            if sub_match:
                msg_otp = sub_match.group(1)

            else:
                body_match = re.search(
                    r'\b([0-9]{4,8})\b'
                    r'(?:\s+is\s+your|\s+is\s+the|'
                    r'[\s\w\-]{0,25}verification)',
                    clean_text,
                    re.IGNORECASE
                )

                if body_match:
                    msg_otp = body_match.group(1)

                else:
                    numbers = re.findall(
                        r'\b[0-9]{4,8}\b',
                        clean_text
                    )

                    valid_nums = [
                        n for n in numbers
                        if not n.startswith('2026')
                        and not n.startswith('7860')
                        and len(n) in [4, 5, 6]
                    ]

                    if valid_nums:
                        msg_otp = valid_nums[0]

            if idx == 0 and msg_otp != "N/A":
                latest_otp = msg_otp
                target_msg = msg

            elif latest_otp == "------" and msg_otp != "N/A":
                latest_otp = msg_otp
                target_msg = msg

            formatted_messages.append({
                "sender": sender_name,
                "email": sender_email,
                "subject": subject,
                "time": received_time,
                "otp": msg_otp,
                "full_message": clean_text
            })

        if latest_otp == "------" and messages_data:
            target_msg = messages_data[0]

        primary_sender = target_msg.get(
            'from', {}
        ).get(
            'emailAddress', {}
        ).get('address', 'Unknown Sender')

        primary_subject = target_msg.get(
            'subject', 'No Subject'
        )

        primary_body_raw = target_msg.get(
            'body', {}
        ).get('content', '')

        primary_body_clean = re.sub(
            '<[^<]+?>', ' ', primary_body_raw
        )

        primary_body_clean = html.unescape(
            primary_body_clean
        )

        primary_body_clean = re.sub(
            r'\s+', ' ', primary_body_clean
        ).strip()

        return jsonify({
            "email": extracted_email,
            "sender": primary_sender,
            "subject": primary_subject,
            "otp": latest_otp,
            "full_message": primary_body_clean,
            "messages_list": formatted_messages
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# NEW USERNAME & PASSWORD GENERATOR
# ==========================================

@app.route('/api/generate', methods=['POST'])
def generate_credentials():

    try:
        data = request.get_json(silent=True) or {}

        count = int(data.get('count', 10))

        username_length = int(
            data.get('username_length', 8)
        )

        password_length = int(
            data.get('password_length', 10)
        )

        if not 1 <= count <= 500:
            return jsonify({
                "error": "Count must be between 1 and 500."
            }), 400

        if not 2 <= username_length <= 12:
            return jsonify({
                "error": "Username must be 2-12 characters."
            }), 400

        if not 4 <= password_length <= 12:
            return jsonify({
                "error": "Password must be 4-12 characters."
            }), 400

        records = []
        seen_usernames = set()

        while len(records) < count:

            username = generate_random_value(
                username_length
            )

            if username.lower() in seen_usernames:
                continue

            seen_usernames.add(username.lower())

            password = generate_random_value(
                password_length
            )

            records.append({
                "username": username,
                "password": password
            })

        return jsonify({
            "success": True,
            "count": len(records),
            "records": records
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# ==========================================
# NEW CSV EXPORT SYSTEM
# ==========================================

@app.route('/api/export', methods=['POST'])
def export_credentials():

    try:
        data = request.get_json(silent=True) or {}

        records = data.get('records', [])

        if not isinstance(records, list):
            return jsonify({
                "error": "Invalid records."
            }), 400

        if len(records) > 5000:
            return jsonify({
                "error": "Maximum 5000 records allowed."
            }), 400

        output = io.StringIO()

        writer = csv.writer(output)

        writer.writerow([
            "Username",
            "Password"
        ])

        for row in records:

            if isinstance(row, dict):

                username = str(
                    row.get('username', '')
                )[:12]

                password = str(
                    row.get('password', '')
                )[:12]

                writer.writerow([
                    username,
                    password
                ])

        return Response(
            output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={
                "Content-Disposition":
                "attachment; filename=generated-credentials.csv"
            }
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route('/health', methods=['GET'])
def health_check():

    return jsonify({
        "status": "online",
        "otp_system": True,
        "generator_system": True
    })


# ==========================================
# APPLICATION START
# ==========================================

if __name__ == '__main__':

    port = int(os.environ.get('PORT', 5000))

    app.run(
        host='0.0.0.0',
        port=port
    )
