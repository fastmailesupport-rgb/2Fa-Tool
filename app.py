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
            
        # --- অত্যন্ত শক্তিশালী রিয়েল ওটিপি ডিটেকশন লজিক ---
        target_msg = messages_data[0]
        otp_code = "N/A"
        
        # প্রথমে চেক করা যাক কোনো মেইলে Twitter/X বা Verification Code এর রিয়েল মেইল আছে কি না
        for msg in messages_data:
            subject = msg.get('subject', '')
            sender_name = msg.get('from', {}).get('emailAddress', {}).get('name', '')
            sender_email = msg.get('from', {}).get('emailAddress', {}).get('address', '')
            body_content = msg.get('body', {}).get('content', '')
            clean_text = re.sub('<[^<]+?>', ' ', body_content)
            
            full_content = (subject + " " + sender_name + " " + sender_email + " " + clean_text).lower()
            
            # যদি টুইটার বা ভেরিফিকেশন কোডের মেইল হয়
            if 'twitter' in full_content or 'x' in full_content or 'verification code' in full_content or 'is your' in full_content:
                # কোড খোঁজার প্যাটার্ন (যেমন: 872261 is your...)
                code_match = re.search(r'\b([0-9]{5,6})\b', clean_text)
                if code_match:
                    target_msg = msg
                    otp_code = code_match.group(1)
                    break

        # যদি ওপরের শর্তে সরাসরি না মেলে, তবে লেটেস্ট মেইলগুলো থেকে সবচেয়ে নিখুঁত ৬ ডিজিটের কোডটি বের করা
        if otp_code == "N/A":
            for msg in messages_data:
                body_content = msg.get('body', {}).get('content', '')
                clean_text = re.sub('<[^<]+?>', ' ', body_content)
                # ৬ ডিজিটের সংখ্যা খোঁজা (যেগুলো সাধারণত ওটিপি হয়)
                digits_6 = re.findall(r'\b[0-9]{6}\b', clean_text)
                if digits_6:
                    target_msg = msg
                    otp_code = digits_6[0]
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
