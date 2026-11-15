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

        # মাইক্রোসফট গ্রাফ এপিআই থেকে সাম্প্রতিক ১৫টি মেসেজ ফেচ করা (যাতে কোনো লেটেস্ট মেইল মিস না হয়)
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
            
        # সেন্ডারের নাম বা সাবজেক্টে 'X' বা 'Twitter' অথবা ভেরিফিকেশন কোড আছে এমন লেটেস্ট মেইলটি খুঁজে বের করা
        target_msg = messages_data[0] # ডিফল্টভাবে সবচেয়ে লেটেস্ট মেইল
        
        for msg in messages_data:
            sender_name = msg.get('from', {}).get('emailAddress', {}).get('name', '').lower()
            sender_email = msg.get('from', {}).get('emailAddress', {}).get('address', '').lower()
            subject = msg.get('subject', '').lower()
            body = msg.get('body', {}).get('content', '')
            
            # যদি টুইটার/এক্স বা কোড রিলেটেড কিওয়ার্ড থাকে, তাকে প্রধান অগ্রাধিকার দেওয়া
            if 'twitter' in sender_name or 'x' in sender_name or 'twitter' in sender_email or 'verification' in subject or 'code' in subject or 'otp' in subject or 'confirmation' in subject:
                target_msg = msg
                break

        sender = target_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = target_msg.get('subject', 'No Subject')
        body_content = target_msg.get('body', {}).get('content', '')
        
        # HTML ট্যাগ পরিষ্কার করে শুধু টেক্সট রাখা
        clean_text = re.sub('<[^<]+?>', ' ', body_content)
        
        # ওটিপি বা কোড খুঁজে বের করার লজিক (৪, ৫ বা ৬ ডিজিটের কোড নিখুঁতভাবে ধরতে)
        otp_match = re.search(r'\b\d{6}\b', clean_text) or re.search(r'\b\d{5}\b', clean_text) or re.search(r'\b\d{4}\b', clean_text)
        otp_code = otp_match.group(0) if otp_match else "N/A"
        
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
