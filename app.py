from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import html
from datetime import datetime

app = Flask(__name__)
CORS(app)

def get_access_token(refresh_token, client_id):
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/.default"
    }
    try:
        res = requests.post(token_url, data=payload, timeout=20)
        data = res.json() if res.text else {}
        if res.status_code == 200 and data.get("access_token"):
            return data.get("access_token"), None
        err_desc = data.get("error_description") or data.get("error") or res.text
        return None, f"Token refresh failed ({res.status_code}): {err_desc}"
    except Exception as e:
        return None, f"Token request exception: {str(e)}"

def extract_otp_from_text(subject, clean_text):
    subj = str(subject or "")
    body = str(clean_text or "")

    # ১. সাবজেক্ট থেকে কোড খোঁজা (যেমন 123456 বা G-123456)
    sub_prefix_match = re.search(r'(?:[A-Z]{1,4}-)?\b([0-9]{4,8})\b', subj)
    if sub_prefix_match:
        candidate = sub_prefix_match.group(1)
        if not candidate.startswith(('2024', '2025', '2026', '2027')):
            return candidate

    # ২. বডি বা সাবজেক্টে verification / code / otp / pin কিওয়ার্ডের কাছাকাছি কোড
    combined = f"{subj} {body}"
    kw_patterns = [
        r'(?:code|otp|pin|verification|verify|security\s*code|login\s*code)[^\d]{0,25}([0-9]{4,8})\b',
        r'\b([0-9]{4,8})\b[^\w\n]{0,25}(?:is\s+your|is\s+the|verification|security|login|code|otp)'
    ]
    for pat in kw_patterns:
        m = re.search(pat, combined, re.IGNORECASE)
        if m:
            candidate = m.group(1)
            if not candidate.startswith(('2024', '2025', '2026', '2027')):
                return candidate

    # ৩. সাধারণ ভ্যালিড সংখ্যা খোঁজা (৪ থেকে ৮ ডিজিট)
    numbers = re.findall(r'\b[0-9]{4,8}\b', combined)
    valid_nums = [
        n for n in numbers
        if not n.startswith(('2024', '2025', '2026', '2027', '7860'))
        and len(n) in [4, 5, 6, 7, 8]
    ]
    if valid_nums:
        return valid_nums[0]

    return "N/A"

def fetch_folder_messages(folder_url, headers):
    try:
        r = requests.get(folder_url, headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json().get('value', []), None
        return [], f"Graph API error ({r.status_code}): {r.text}"
    except Exception as e:
        return [], f"Graph API exception: {str(e)}"

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "message": "Mail OTP server is running"}), 200

@app.route('/get-otp', methods=['POST'])
def get_otp():
    try:
        data = request.get_json(silent=True) or {}
        raw_input = str(data.get('token', '')).strip()

        if not raw_input:
            return jsonify({"error": "Token is missing"}), 400

        extracted_email = "Unknown"
        access_token = None
        token_error = None
        has_pipe_format = '|' in raw_input

        # টোকেন ফরম্যাট থেকে ডেটা আলাদা করা: email|pass|refresh_token|client_id
        if has_pipe_format:
            parts = [p.strip() for p in raw_input.split('|')]
            if len(parts) >= 4:
                extracted_email = parts[0]
                refresh_token = parts[2]
                client_id = parts[3]
                access_token, token_error = get_access_token(refresh_token, client_id)
            elif len(parts) == 2:
                access_token, token_error = get_access_token(parts[0], parts[1])
            else:
                return jsonify({
                    "error": "Invalid token format. Expected email|password|refresh_token|client_id"
                }), 400
        else:
            access_token = raw_input

        if not access_token:
            return jsonify({
                "error": "Failed to generate access token from refresh token",
                "details": token_error or "Unknown token error"
            }), 401

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        # Inbox ও JunkEmail উভয় ফোল্ডার থেকে সাম্প্রতিক মেসেজ আনা
        inbox_url = 'https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages?$top=15&$orderby=receivedDateTime desc'
        junk_url = 'https://graph.microsoft.com/v1.0/me/mailFolders/JunkEmail/messages?$top=10&$orderby=receivedDateTime desc'

        inbox_msgs, inbox_err = fetch_folder_messages(inbox_url, headers)
        junk_msgs, _ = fetch_folder_messages(junk_url, headers)

        if inbox_err and not inbox_msgs and not junk_msgs:
            # ফলব্যাক হিসেবে সরাসরি /me/messages চেক করা
            fallback_msgs, fb_err = fetch_folder_messages(
                'https://graph.microsoft.com/v1.0/me/messages?$top=15&$orderby=receivedDateTime desc',
                headers
            )
            if fb_err and not fallback_msgs:
                return jsonify({
                    "error": "Invalid or expired token",
                    "details": fb_err
                }), 401
            messages_data = fallback_msgs
        else:
            merged = []
            seen_ids = set()
            for m in (inbox_msgs + junk_msgs):
                mid = m.get('id')
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)
                merged.append(m)

            def parse_dt(item):
                dt_str = item.get('receivedDateTime') or ''
                try:
                    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                except Exception:
                    return datetime.min

            merged.sort(key=parse_dt, reverse=True)
            messages_data = merged[:15]

        if not messages_data:
            return jsonify({
                "email": extracted_email,
                "sender": "No Messages",
                "subject": "Inbox is empty",
                "otp": "------",
                "full_message": "No recent messages found in Inbox or Junk folder.",
                "messages_list": []
            })

        formatted_messages = []
        latest_otp = "------"
        target_msg = messages_data[0]

        for idx, msg in enumerate(messages_data):
            sender_email = msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
            sender_name = msg.get('from', {}).get('emailAddress', {}).get('name', sender_email)
            subject = msg.get('subject', 'No Subject')
            received_time = msg.get('receivedDateTime', '')
            body_content = msg.get('body', {}).get('content', '')

            clean_text = re.sub('<[^<]+?>', ' ', body_content)
            clean_text = html.unescape(clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()

            msg_otp = extract_otp_from_text(subject, clean_text)

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

        primary_sender = target_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        primary_subject = target_msg.get('subject', 'No Subject')
        primary_body_raw = target_msg.get('body', {}).get('content', '')

        primary_body_clean = re.sub('<[^<]+?>', ' ', primary_body_raw)
        primary_body_clean = html.unescape(primary_body_clean)
        primary_body_clean = re.sub(r'\s+', ' ', primary_body_clean).strip()

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
