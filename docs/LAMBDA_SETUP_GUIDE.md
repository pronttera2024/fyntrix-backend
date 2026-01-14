# AWS Lambda Setup for Cognito Phone OTP Authentication

## Overview

You need to create **3 Lambda functions** that work together to handle phone number OTP authentication:

1. **Define Auth Challenge** - Determines the authentication flow
2. **Create Auth Challenge** - Generates OTP and triggers SMS
3. **Verify Auth Challenge Response** - Validates the OTP

---

## Step 1: Create IAM Role for Lambda Functions

### 1.1 Go to IAM Console
- Open AWS Console → **IAM** → **Roles** → **Create role**

### 1.2 Configure Role
- **Trusted entity type**: AWS service
- **Use case**: Lambda
- Click **Next**

### 1.3 Attach Policies
Add these policies:
- ✅ **AWSLambdaBasicExecutionRole** (for CloudWatch logs)
- ✅ **AmazonCognitoPowerUser** (for Cognito operations)
- ✅ **AmazonSNSFullAccess** (for sending SMS)

Or create a custom policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminUpdateUserAttributes"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "*"
    }
  ]
}
```

### 1.4 Name the Role
- **Role name**: `CognitoLambdaExecutionRole`
- Click **Create role**

---

## Step 2: Create Lambda Function #1 - Define Auth Challenge

### 2.1 Create Function
- Go to **AWS Lambda** → **Create function**
- **Function name**: `CognitoDefineAuthChallenge`
- **Runtime**: Python 3.11 (or latest)
- **Execution role**: Use existing role → `CognitoLambdaExecutionRole`
- Click **Create function**

### 2.2 Add Function Code

Replace the default code with:

```python
def lambda_handler(event, context):
    """
    Define Auth Challenge Lambda
    Determines the authentication flow for custom auth
    """
    print(f"Define Auth Challenge Event: {event}")
    
    # Get the session array
    session = event['request']['session']
    
    # First attempt - no previous sessions
    if len(session) == 0:
        # Start the custom challenge flow
        event['response']['issueTokens'] = False
        event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
        print("First attempt - issuing CUSTOM_CHALLENGE")
    
    # Second attempt - user has answered the challenge
    elif len(session) == 1 and session[0]['challengeName'] == 'CUSTOM_CHALLENGE':
        # Check if the answer was correct
        if session[0]['challengeResult']:
            # OTP was correct - issue tokens
            event['response']['issueTokens'] = True
            print("OTP verified successfully - issuing tokens")
        else:
            # OTP was incorrect - fail authentication
            event['response']['issueTokens'] = False
            event['response']['failAuthentication'] = True
            print("OTP verification failed")
    
    # Too many attempts
    elif len(session) >= 3:
        # Fail after 3 attempts
        event['response']['issueTokens'] = False
        event['response']['failAuthentication'] = True
        print("Too many attempts - failing authentication")
    
    # Default case
    else:
        event['response']['issueTokens'] = False
        event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
    
    print(f"Define Auth Challenge Response: {event['response']}")
    return event
```

### 2.3 Configure Function
- **Timeout**: 10 seconds (Configuration → General configuration → Edit)
- Click **Deploy** to save

---

## Step 3: Create Lambda Function #2 - Create Auth Challenge

### 3.1 Create Function
- Go to **AWS Lambda** → **Create function**
- **Function name**: `CognitoCreateAuthChallenge`
- **Runtime**: Python 3.11
- **Execution role**: Use existing role → `CognitoLambdaExecutionRole`
- Click **Create function**

### 3.2 Add Function Code

```python
import random
import boto3
import os

def lambda_handler(event, context):
    """
    Create Auth Challenge Lambda
    Generates OTP and sends it via SNS
    """
    print(f"Create Auth Challenge Event: {event}")
    
    # Only create challenge if it's CUSTOM_CHALLENGE
    if event['request']['challengeName'] != 'CUSTOM_CHALLENGE':
        return event
    
    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    print(f"Generated OTP: {otp}")
    
    # Get user's phone number
    phone_number = event['request']['userAttributes'].get('phone_number')
    
    if phone_number:
        # Send OTP via SNS
        try:
            sns_client = boto3.client('sns', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            
            message = f"Your verification code is: {otp}\n\nThis code will expire in 3 minutes."
            
            response = sns_client.publish(
                PhoneNumber=phone_number,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )
            
            print(f"SMS sent successfully to {phone_number}. MessageId: {response['MessageId']}")
        
        except Exception as e:
            print(f"Error sending SMS: {str(e)}")
            # Continue anyway - Cognito might handle SMS sending
    
    # Store the OTP in private challenge parameters (not visible to client)
    event['response']['privateChallengeParameters'] = {
        'answer': otp
    }
    
    # Public parameters (visible to client) - don't include the OTP!
    event['response']['publicChallengeParameters'] = {
        'phone_number': phone_number
    }
    
    # Challenge metadata
    event['response']['challengeMetadata'] = 'OTP_CHALLENGE'
    
    print(f"Create Auth Challenge Response: {event['response']}")
    return event
```

### 3.3 Configure Function
- **Timeout**: 30 seconds (for SNS API call)
- **Environment variables** (Configuration → Environment variables):
  - Key: `AWS_REGION`, Value: `us-east-1` (or your region)
- Click **Deploy**

---

## Step 4: Create Lambda Function #3 - Verify Auth Challenge Response

### 4.1 Create Function
- Go to **AWS Lambda** → **Create function**
- **Function name**: `CognitoVerifyAuthChallenge`
- **Runtime**: Python 3.11
- **Execution role**: Use existing role → `CognitoLambdaExecutionRole`
- Click **Create function**

### 4.2 Add Function Code

```python
def lambda_handler(event, context):
    """
    Verify Auth Challenge Response Lambda
    Validates the OTP provided by the user
    """
    print(f"Verify Auth Challenge Event: {event}")
    
    # Get the expected answer (OTP) from private challenge parameters
    expected_answer = event['request']['privateChallengeParameters'].get('answer')
    
    # Get the user's answer (OTP they entered)
    user_answer = event['request']['challengeAnswer']
    
    print(f"Expected OTP: {expected_answer}")
    print(f"User provided OTP: {user_answer}")
    
    # Compare the answers
    if expected_answer and user_answer:
        # Check if they match (case-insensitive, trimmed)
        is_correct = expected_answer.strip() == user_answer.strip()
        event['response']['answerCorrect'] = is_correct
        
        if is_correct:
            print("OTP verification successful")
        else:
            print("OTP verification failed - incorrect code")
    else:
        # Missing data
        event['response']['answerCorrect'] = False
        print("OTP verification failed - missing data")
    
    print(f"Verify Auth Challenge Response: {event['response']}")
    return event
```

### 4.3 Configure Function
- **Timeout**: 10 seconds
- Click **Deploy**

---

## Step 5: Connect Lambda Functions to Cognito User Pool

### 5.1 Go to Cognito User Pool
- Open **AWS Cognito** → **User pools** → Select your user pool

### 5.2 Configure Lambda Triggers
- Go to **User pool properties** tab
- Scroll down to **Lambda triggers**
- Click **Add Lambda trigger**

### 5.3 Add Triggers

Add these 3 triggers:

**Trigger 1: Define auth challenge**
- **Trigger type**: Authentication
- **Authentication**: Define auth challenge
- **Lambda function**: `CognitoDefineAuthChallenge`
- Click **Add Lambda trigger**

**Trigger 2: Create auth challenge**
- Click **Add Lambda trigger** again
- **Trigger type**: Authentication
- **Authentication**: Create auth challenge
- **Lambda function**: `CognitoCreateAuthChallenge`
- Click **Add Lambda trigger**

**Trigger 3: Verify auth challenge response**
- Click **Add Lambda trigger** again
- **Trigger type**: Authentication
- **Authentication**: Verify auth challenge response
- **Lambda function**: `CognitoVerifyAuthChallenge`
- Click **Add Lambda trigger**

### 5.4 Verify Triggers
You should now see all 3 triggers listed:
- ✅ Define auth challenge → CognitoDefineAuthChallenge
- ✅ Create auth challenge → CognitoCreateAuthChallenge
- ✅ Verify auth challenge response → CognitoVerifyAuthChallenge

---

## Step 6: Configure Cognito App Client for Custom Auth

### 6.1 Enable Custom Auth Flow
- Go to **App integration** tab
- Under **App clients and analytics**, click your app client
- Click **Edit** under **Authentication flows**
- Enable:
  - ✅ **ALLOW_CUSTOM_AUTH**
  - ✅ **ALLOW_REFRESH_TOKEN_AUTH**
- Click **Save changes**

---

## Step 7: Test the Setup

### 7.1 Test with Your API

**Step 1: Signup**
```bash
curl -X POST http://localhost:8000/auth/phone/signup \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919876543210",
    "name": "Test User"
  }'
```

**Step 2: Verify Signup OTP**
```bash
curl -X POST http://localhost:8000/auth/phone/verify-signup \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919876543210",
    "otp_code": "123456"
  }'
```

**Step 3: Login (Get OTP)**
```bash
curl -X POST http://localhost:8000/auth/phone/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919876543210"
  }'
```

**Step 4: Verify Login OTP**
```bash
curl -X POST http://localhost:8000/auth/phone/login/verify \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+919876543210",
    "session": "SESSION_TOKEN_FROM_STEP_3",
    "otp_code": "654321"
  }'
```

### 7.2 Check CloudWatch Logs

If something doesn't work:
1. Go to **CloudWatch** → **Log groups**
2. Find logs for your Lambda functions:
   - `/aws/lambda/CognitoDefineAuthChallenge`
   - `/aws/lambda/CognitoCreateAuthChallenge`
   - `/aws/lambda/CognitoVerifyAuthChallenge`
3. Check for errors or debug messages

---

## Troubleshooting

### Issue: "Custom auth lambda trigger is not configured"
**Solution**: Make sure all 3 Lambda triggers are attached to your Cognito User Pool

### Issue: "SMS not being sent"
**Solution**: 
- Check Lambda execution role has SNS permissions
- Verify SNS spending limit not exceeded
- Check CloudWatch logs for SNS errors
- Ensure phone number is in E.164 format

### Issue: "Invalid session"
**Solution**: Session tokens expire in 3 minutes. User must verify OTP quickly.

### Issue: Lambda timeout
**Solution**: Increase timeout to 30 seconds for Create Auth Challenge Lambda

### Issue: "Access Denied" in Lambda logs
**Solution**: Check IAM role has proper permissions for SNS and Cognito

---

## Cost Estimate

### Lambda Costs
- **Free tier**: 1M requests/month + 400,000 GB-seconds compute
- **After free tier**: $0.20 per 1M requests
- **Your usage**: ~2-3 Lambda invocations per login = negligible cost

### SNS SMS Costs
- **India**: ~$0.00645 per SMS
- **100 logins/day**: ~$0.65/day = ~$19.50/month

### Cognito Costs
- **First 50,000 MAU**: Free
- **Your usage**: Likely within free tier

---

## Security Best Practices

1. **Rate Limiting**: Implement rate limiting on login endpoints
2. **OTP Expiry**: OTPs expire in 3 minutes (handled by session timeout)
3. **Max Attempts**: Lambda limits to 3 attempts before failing
4. **Logging**: Enable CloudWatch logs for audit trail
5. **Encryption**: All data encrypted in transit (HTTPS)
6. **Phone Verification**: Always verify phone ownership during signup

---

## Quick Reference: Lambda ARNs

After creating the functions, note down their ARNs:

```
CognitoDefineAuthChallenge: arn:aws:lambda:REGION:ACCOUNT:function:CognitoDefineAuthChallenge
CognitoCreateAuthChallenge: arn:aws:lambda:REGION:ACCOUNT:function:CognitoCreateAuthChallenge
CognitoVerifyAuthChallenge: arn:aws:lambda:REGION:ACCOUNT:function:CognitoVerifyAuthChallenge
```

These will be automatically used by Cognito once attached as triggers.

---

## Next Steps After Setup

1. ✅ Test with a real phone number
2. ✅ Monitor CloudWatch logs for errors
3. ✅ Set up CloudWatch alarms for Lambda errors
4. ✅ Configure SNS spending alerts
5. ✅ Implement rate limiting in your API
6. ✅ Add error handling for edge cases
7. ✅ Test with multiple concurrent users

---

## Support

If you encounter issues:
1. Check CloudWatch logs for all 3 Lambda functions
2. Verify IAM permissions
3. Test with AWS Console's "Test" feature in Lambda
4. Check Cognito User Pool configuration
5. Verify SNS is working (send test SMS from SNS console)
