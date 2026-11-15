from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)  # ফন্টএন্ড থেকে রিকোয়েস্ট রিসিভ করার জন্য CORS এনাবল করা হলো

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

        # ফরম্যাট চেক করা: email|pass|refresh_token|client_id
        if '|' in raw_input:
            parts = [p.strip() for p in raw_input.split('|')]
            if len(parts) >= 4:
                extracted_email = parts[0]
                refresh_token = parts[2]
                client_id = parts[3]
                
                # রেন্ডার ব্যাকএন্ড থেকে রিফ্রেশ টোকেন দিয়ে নতুন অ্যাক্সেস টোকেন আনা
                access_token = get_access_token(refresh_token, client_id)
            elif len(parts) == 2:
                # যদি শুধু টোকেন আর ক্লায়েন্ট আইডি থাকে
                access_token = get_access_token(parts[0], parts[1])

        # যদি কোনো কারণে উপর্যুক্ত নিয়মে না হয়, তবে পুরো ইনপুটকেই টোকেন হিসেবে ট্রাই করা
        if not access_token:
            access_token = raw_input

        # মাইক্রোসফট গ্রাফ এপিআই (Microsoft Graph API) ব্যবহার করে ইনবক্সের মেসেজ ফেচ করা
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        graph_url = 'https://graph.microsoft.com/v1.0/me/messages?$top=5&$orderby=receivedDateTime desc'
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
            
        # লেটেস্ট মেইলটি নেওয়া
        latest_msg = messages_data[0]
        sender = latest_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = latest_msg.get('subject', 'No Subject')
        body_content = latest_msg.get('body', {}).get('content', '')
        
        # HTML ট্যাগ পরিষ্কার করে শুধু টেক্সট রাখা
        clean_text = re.sub('<[^<]+?>', ' ', body_content)
        
        # ওটিপি বা কোড খুঁজে বের করা (৪ বা ৬ ডিজিটের কোড)
        otp_match = re.search(r'\b\d{6}\b', clean_text) or re.search(r'\b\d{4}\b', clean_text)
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
