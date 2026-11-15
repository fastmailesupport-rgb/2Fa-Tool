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
            
        # --- সুনির্দিষ্ট ওটিপি মেইল ফিল্টারিং লজিক ---
        target_msg = messages_data[0]
        otp_code = "N/A"
        
        # ১. প্রথমে এমন মেইল খোঁজা যাতে পরিষ্কারভাবে verification code বা is your লেখা আছে
        found_otp_mail = False
        for msg in messages_data:
            subject = msg.get('subject', '')
            body_content = msg.get('body', {}).get('content', '')
            clean_text = re.sub('<[^<]+?>', ' ', body_content)
            full_text = (subject + " " + clean_text).lower()
            
            if 'verification code' in full_text or 'is your' in full_text or 'confirm' in full_text:
                # মেইলের ভেতর থেকে ৪ থেকে ৮ ডিজিটের কোড বের করা
                code_match = re.search(r'\b([0-9]{5,6})\b', clean_text)
                if code_match:
                    target_msg = msg
                    otp_code = code_match.group(1)
                    found_otp_mail = True
                    break

        # ২. যদি উপর্যুক্ত শর্তে মেইল না পাওয়া যায়, তবে লেটেস্ট মেসেজগুলো থেকে ৬ ডিজিটের ভ্যালিড কোড খোঁজা
        if not found_otp_mail:
            for msg in messages_data:
                body_content = msg.get('body', {}).get('content', '')
                clean_text = re.sub('<[^<]+?>', ' ', body_content)
                # ওয়েলকাম মেইল বা অন্য সাধারণ টেক্সট বাদ দিয়ে যেখানে কোড থাকার সম্ভাবনা বেশি
                digits = re.findall(r'\b[0-9]{6}\b', clean_text)
                if digits:
                    target_msg = msg
                    otp_code = digits[0]
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
