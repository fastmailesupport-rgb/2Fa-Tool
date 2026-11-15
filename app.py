from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)  # ফন্টএন্ড থেকে রিকোয়েস্ট রিসিভ করার জন্য CORS এনাবল করা হলো

@app.route('/get-otp', methods=['POST'])
def get_otp():
    try:
        data = request.json
        raw_input = data.get('token', '').strip()
        
        if not raw_input:
            return jsonify({"error": "Token is missing"}), 400

        # ইনপুট থেকে আসল Access Token খুঁজে বের করার লজিক (EyJ... দিয়ে শুরু টোকেন)
        token_match = re.search(r'(Ew[a-zA-Z0-9_\-\.]+|eyJ[a-zA-Z0-9_\-\.]+)', raw_input)
        
        if token_match:
            token = token_match.group(0)
        else:
            # যদি সরাসরি টোকেন দেয় অথবা পাইপ (|) বা কোলন (:) দিয়ে আলাদা করা থাকে
            parts = re.split(r'[\|\:\s]+', raw_input)
            token = parts[-1] if len(parts) > 0 else raw_input

        # মাইক্রোসফট গ্রাফ এপিআই (Microsoft Graph API) ব্যবহার করে ইনবক্সের মেসেজ ফেচ করা
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # সাম্প্রতিক মেসেজগুলোর জন্য মাইক্রোসফট গ্রাফ এন্ডপয়েন্ট
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
                "email": "Connected",
                "sender": "No Messages",
                "subject": "Inbox is empty",
                "otp": "------",
                "full_message": "No recent messages found in this Outlook/Hotmail inbox."
            })
            
        # সবচেয়ে শেষের (লেটেস্ট) মেইলটি নেওয়া
        latest_msg = messages_data[0]
        sender = latest_msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown Sender')
        subject = latest_msg.get('subject', 'No Subject')
        body_content = latest_msg.get('body', {}).get('content', '')
        
        # বডি থেকে ওটিপি বা কোড খুঁজে বের করার লজিক
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
