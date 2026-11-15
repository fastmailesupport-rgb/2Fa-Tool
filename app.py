from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import html

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
        res = requests.post(token_url, data=payload)
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception as e:
        print("Token generation error:", str(e))
    return None

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
        
        graph_url = 'https://graph.microsoft.com/v1.0/me/messages?$top=15&$orderby=receivedDateTime desc'
        response = requests.get(graph_url, headers=headers)
        
        if response.status_code != 200:
            return jsonify({"error": "Invalid or expired token", "details": response.text}), 401
            
        messages_data = response.json().get('value', [])
        
        if not messages_data:
            return jsonify({
                "email": extracted_email,
                "sender": "No Messages",
                "subject": "Inbox is empty",
                "otp": "------",
                "full_message": "No recent messages found.",
                "messages_list": []
            })
            
        formatted_messages = []
        latest_otp = "------"
        
        for idx, msg in enumerate(messages_data):
            sender_email = msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
            sender_name = msg.get('from', {}).get('emailAddress', {}).get('name', sender_email)
            subject = msg.get('subject', 'No Subject')
            received_time = msg.get('receivedDateTime', '')
            body_content = msg.get('body', {}).get('content', '')
            
            # HTML ট্যাগ এবং &nbsp; বা অন্যান্য এন্টাইটি পরিষ্কার করা
            clean_text = re.sub('<[^<]+?>', ' ', body_content)
            clean_text = html.unescape(clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # ওটিপি কোড খোঁজা (৪ থেকে ৮ ডিজিট)
            msg_otp = "N/A"
            numbers = re.findall(r'\b[0-9]{4,8}\b', clean_text)
            valid_nums = [n for n in numbers if not n.startswith('2026') and len(n) >= 4]
            if valid_nums:
                msg_otp = valid_nums[0]
            
            if idx == 0 and msg_otp != "N/A":
                latest_otp = msg_otp
            elif latest_otp == "------" and msg_otp != "N/A":
                latest_otp = msg_otp

            formatted_messages.append({
                "sender": sender_name,
                "email": sender_email,
                "subject": subject,
                "time": received_time,
                "otp": msg_otp,
                "full_message": clean_text
            })

        primary_msg = messages_data[0]
        primary_sender = primary_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        primary_subject = primary_msg.get('subject', 'No Subject')
        
        primary_body_raw = primary_msg.get('body', {}).get('content', '')
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
