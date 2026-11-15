from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

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

        # ফরম্যাট থেকে ডেটা আলাদা করা: email|pass|refresh_token|client_id
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

        # মাইক্রোসফট গ্রাফ এপিআই থেকে ইনবক্সের মেসেজগুলো আনা
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        graph_url = 'https://graph.microsoft.com/v1.0/me/messages?$top=20&$orderby=receivedDateTime desc'
        response = requests.get(graph_url, headers=headers)
        
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
                "full_message": "No recent messages found in this inbox."
            })
            
        # --- অতি নিখুঁত ওটিপি এক্সট্রাকশন লজিক ---
        target_msg = messages_data[0]
        otp_code = "N/A"
        
        for msg in messages_data:
            subject = msg.get('subject', '')
            body_content = msg.get('body', {}).get('content', '')
            clean_text = re.sub('<[^<]+?>', ' ', body_content)
            
            # ১. প্রথমে সাবজেক্ট থেকে ৬ ডিজিটের কোড খোঁজা (যেমন: "872261 is your X verification code")
            sub_match = re.search(r'\b([0-9]{6})\b', subject)
            if sub_match:
                target_msg = msg
                otp_code = sub_match.group(1)
                break
            
            # ২. বডি থেকে কোডের নির্দিষ্ট প্যাটার্ন খোঁজা
            body_match = re.search(r'\b([0-9]{6})\b(?:\s+is\s+your|\s+is\s+the|[\s\w\-]{0,25}verification)', clean_text, re.IGNORECASE)
            if body_match:
                target_msg = msg
                otp_code = body_match.group(1)
                break
                
            # ৩. যদি এক্স/টুইটার বা অন্য ভেরিফিকেশন মেইল হয়
            if 'x' in msg.get('from', {}).get('emailAddress', {}).get('address', '').lower() or 'twitter' in subject.lower():
                all_6_digits = re.findall(r'\b([0-9]{6})\b', clean_text)
                if all_6_digits:
                    target_msg = msg
                    otp_code = all_6_digits[0]
                    break

        sender = target_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = target_msg.get('subject', 'No Subject')
        body_content = target_msg.get('body', {}).get('content', '')
        clean_text = re.sub('<[^<]+?>', ' ', body_content)

        return jsonify({
            "email": extracted_email,
            "sender": sender,
            "subject": subject,
            "otp": otp_code,
            "full_message": clean_text.strip()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
