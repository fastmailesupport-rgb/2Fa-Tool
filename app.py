from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)

@app.route('/get-otp', methods=['POST'])
def get_otp():
    try:
        data = request.json
        raw_input = data.get('token', '').strip()
        
        if not raw_input:
            return jsonify({"error": "Token or credentials missing"}), 400

        # ইনপুট থেকে টোকেন বা পাসওয়ার্ড আলাদা করার চেষ্টা
        token = raw_input
        # যদি পাইপ বা অন্য কিছু থাকে, শেষের অংশটি টোকেন হতে পারে
        if '|' in raw_input:
            parts = [p.strip() for p in raw_input.split('|')]
            # সাধারণত শেষের বা বড় স্ট্রিংগুলো টোকেন হয়
            for p in reversed(parts):
                if len(p) > 20:
                    token = p
                    break

        # মাইক্রোসফট গ্রাফ এপিআই কল
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        graph_url = 'https://graph.microsoft.com/v1.0/me/messages?$top=5&$orderby=receivedDateTime desc'
        response = requests.get(graph_url, headers=headers)
        
        # যদি সরাসরি অ্যাক্সেস টোকেন কাজ না করে এবং রিফ্রেশ টোকেন হ্যান্ডেল করতে হয়
        if response.status_code != 200:
            return jsonify({
                "error": "Invalid or expired token", 
                "details": response.text
            }), 401
            
        messages_data = response.json().get('value', [])
        
        if not messages_data:
            return jsonify({
                "sender": "No Messages",
                "subject": "Inbox is empty",
                "otp": "------",
                "full_message": "No recent messages found in this inbox."
            })
            
        latest_msg = messages_data[0]
        sender = latest_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = latest_msg.get('subject', 'No Subject')
        body_content = latest_msg.get('body', {}).get('content', '')
        
        # ওটিপি বা কোড খুঁজে বের করা (৪ থেকে ৬ ডিজিটের কোড)
        otp_match = re.search(r'\b\d{6}\b', body_content) or re.search(r'\b\d{4}\b', body_content)
        otp_code = otp_match.group(0) if otp_match else "N/A"
        
        return jsonify({
            "sender": sender,
            "subject": subject,
            "otp": otp_code,
            "full_message": body_content
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
