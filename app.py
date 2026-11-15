).get('content', '')
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

if __name__ == justify-content app.run(host='0.0.0.0', port=5000)
