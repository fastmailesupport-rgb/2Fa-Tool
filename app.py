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

        # মাইক্রোসফট গ্রাফ এপিআই থেকে লেটেস্ট মেসেজগুলো আনা
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        graph_url = 'https://graph.microsoft.com/v1.0/me/messages?$top=15&$orderby=receivedDateTime desc'
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
            
        # সবচেয়ে লেটেস্ট এবং রিয়েল সার্ভিস মেইলটি খুঁজে বের করা (যেমন Twitter/X)
        target_msg = messages_data[0]
        for msg in messages_data:
            sender_name = msg.get('from', {}).get('emailAddress', {}).get('name', '').lower()
            sender_email = msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
            subject = msg.get('subject', '').lower()
            
            if any(k in sender_name or k in sender_email or k in subject for k in ['twitter', 'x', 'verification', 'code', 'otp', 'confirm', 'security', 'login']):
                target_msg = msg
                break

        sender = target_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = target_msg.get('subject', 'No Subject')
        body_content = target_msg.get('body', {}).get('content', '')
        
        # HTML ট্যাগ রিমুভ করে ক্লিন টেক্সট তৈরি
        clean_text = re.sub('<[^<]+?>', ' ', body_content)
        
        otp_code = "N/A"
        
        # ১. প্রথমে সাবজেক্ট বা নির্দিষ্ট কীওয়ার্ডের (مثل code, is, pin) আশেপাশের ৪ থেকে ৮ ডিজিটের কোড খোঁজা
        context_match = re.search(r'(?:code|pin|otp|verification|is)[:\s]+([0-9]{4,8})', clean_text, re.IGNORECASE)
        if context_match:
            otp_code = context_match.group(1)
        else:
            # ২. যদি সরাসরি বডিতে আলাদা কোনো ৪ থেকে ৮ ডিজিটের সংখ্যা থাকে (যেমন টুইটারের মূল ওটিপি)
            # এটি এমনভাবে ফিল্টার করা হয়েছে যাতে কোনো স্টাইল বা বড় আইডি কোড না ধরে শুধু ওটিপি ধরে
            all_numbers = re.findall(r'\b[0-9]{4,8}\b', clean_text)
            if all_numbers:
                # সাধারণ দীর্ঘ ট্র্যাকিং বা সিএসএস কোড (৬-৮ ডিজিটের বেশি বা অদ্ভুত সংখ্যা) বাদ দিয়ে সঠিক ওটিপি পিক করা
                valid_otps = [num for num in all_numbers if len(num) in [4, 5, 6, 7, 8] and not num.startswith('2026') and not num.startswith('000')]
                if valid_otps:
                    otp_code = valid_otps[0] # সবচেয়ে প্রথম পাওয়া রিয়েল ওটিপি
                else:
                    otp_code = all_numbers[0]

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
