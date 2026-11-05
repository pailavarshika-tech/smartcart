SmartCart - friend-style cart and Razorpay checkout

1. Extract this ZIP. Open the SmartCart folder in your terminal.
2. Install dependencies: python -m pip install -r requirements.txt
3. Open config.py and add YOUR OWN Razorpay TEST Key ID and Key Secret:
   RAZORPAY_KEY_ID = 'rzp_test_...'
   RAZORPAY_KEY_SECRET = 'your_test_secret'
   Do not use another person's keys.
4. Confirm MySQL is running and smartcart_db plus the existing tables are present.
5. Run: python app.py

Cart flow: select products (checkboxes) -> Proceed -> enter address -> Save and Continue -> Razorpay payment -> order success.
Only selected products are included in the amount. Payment success is verified on the Flask server.

This ZIP does not include a virtual environment. Install dependencies using requirements.txt.
