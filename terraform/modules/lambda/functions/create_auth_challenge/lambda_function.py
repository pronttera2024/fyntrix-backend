"""
Create Auth Challenge Lambda
Generates OTP and sends it via SMS to the user's phone number
"""
import random
import boto3
import os

sns_client = boto3.client('sns')

def lambda_handler(event, context):
    """
    Create a custom auth challenge (OTP via SMS)
    """
    print(f"Create Auth Challenge Event: {event}")
    
    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Get user's phone number
    phone_number = event['request']['userAttributes'].get('phone_number')
    
    if phone_number:
        # Send OTP via SMS
        try:
            message = f"Your Fyntrix verification code is: {otp}. This code will expire in 5 minutes."
            
            sns_client.publish(
                PhoneNumber=phone_number,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )
            
            print(f"OTP sent to {phone_number}")
        except Exception as e:
            print(f"Error sending SMS: {str(e)}")
    
    # Store the OTP in the challenge metadata
    event['response']['publicChallengeParameters'] = {
        'phone': phone_number[-4:] if phone_number else 'N/A'  # Show last 4 digits
    }
    event['response']['privateChallengeParameters'] = {
        'otp': otp
    }
    event['response']['challengeMetadata'] = 'OTP_CHALLENGE'
    
    print(f"Create Auth Challenge Response: {event['response']}")
    return event
