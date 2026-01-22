"""
Verify Auth Challenge Lambda
Verifies the OTP entered by the user
"""

def lambda_handler(event, context):
    """
    Verify the user's answer to the custom challenge (OTP)
    """
    print(f"Verify Auth Challenge Event: {event}")
    
    # Get the expected OTP from the challenge
    expected_otp = event['request']['privateChallengeParameters'].get('otp')
    
    # Get the user's answer
    user_answer = event['request']['challengeAnswer']
    
    # Verify the OTP
    if user_answer == expected_otp:
        event['response']['answerCorrect'] = True
        print("OTP verification successful")
    else:
        event['response']['answerCorrect'] = False
        print(f"OTP verification failed. Expected: {expected_otp}, Got: {user_answer}")
    
    print(f"Verify Auth Challenge Response: {event['response']}")
    return event
