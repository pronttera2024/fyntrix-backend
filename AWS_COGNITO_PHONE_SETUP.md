# AWS Cognito Phone Number Authentication Setup Guide

This guide explains how to configure AWS Cognito for phone number authentication with OTP (One-Time Password) using SNS for SMS delivery.

## Overview

Your application now supports:
- **Signup**: Users sign up with phone number + name, receive OTP via SMS, verify to complete registration
- **Login**: Users login with phone number only, receive OTP via SMS, verify to get auth tokens

## AWS Cognito Configuration Steps

### 1. Configure User Pool Sign-in Options

1. Go to **AWS Console** → **Amazon Cognito** → **User Pools**
2. Select your User Pool (or create a new one)
3. Navigate to **Sign-in experience** tab
4. Under **Cognito user pool sign-in options**:
   - ✅ Enable **Phone number** (allow users to sign in with phone number)
   - ❌ Disable **Email** (if you want phone-only authentication)
   - ❌ Disable **Username** (if you want phone-only authentication)

### 2. Configure Required Attributes

1. Still in **Sign-in experience** tab
2. Under **User name requirements**:
   - Select **Allow users to sign in with a preferred user name**
3. Under **Required attributes**:
   - ✅ **phone_number** (required)
   - ✅ **name** (required)
   - Remove other attributes if not needed

### 3. Configure SNS for SMS Delivery

#### Option A: Using Cognito's Default SMS Configuration (Recommended for Testing)

1. Navigate to **Messaging** tab in your User Pool
2. Under **SMS**:
   - Select **Cognito default SMS**
   - This uses AWS's shared SMS infrastructure
   - **Limitations**: 
     - Limited to 1 SMS per second
     - Not suitable for production
     - Some regions may not be supported

#### Option B: Using SNS with IAM Role (Recommended for Production)

1. **Create IAM Role for Cognito SNS Access**:
   
   Go to **IAM Console** → **Roles** → **Create role**
   
   - **Trusted entity type**: AWS service
   - **Use case**: Cognito
   - **Permissions**: Attach policy `AmazonSNSFullAccess` or create custom policy:
   
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
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
   
   - **Role name**: `CognitoSNSRole`
   - **Trust relationship** should include:
   
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Service": "cognito-idp.amazonaws.com"
         },
         "Action": "sts:AssumeRole"
       }
     ]
   }
   ```

2. **Configure SNS in Cognito**:
   
   Back in your User Pool → **Messaging** tab:
   - Under **SMS**:
     - Select **SNS**
     - **IAM role**: Select the `CognitoSNSRole` you just created
     - **External ID**: (optional, for additional security)

3. **Configure SNS Spending Limits** (Important!):
   
   Go to **SNS Console** → **Text messaging (SMS)** → **Account settings**
   - Set **Account spending limit**: Set appropriate limit (e.g., $10/month)
   - **Default message type**: 
     - **Transactional** (for OTP - higher priority, more expensive)
     - **Promotional** (for marketing - lower priority, cheaper)
   - **Default sender ID**: Your app name (not supported in all countries)

### 4. Configure App Client for Custom Auth Flow

1. Navigate to **App integration** tab
2. Under **App clients and analytics**, select your app client
3. Click **Edit** on **Authentication flows**
4. Enable the following auth flows:
   - ✅ **ALLOW_CUSTOM_AUTH** (required for phone OTP login)
   - ✅ **ALLOW_REFRESH_TOKEN_AUTH** (for token refresh)
   - ✅ **ALLOW_USER_PASSWORD_AUTH** (if you want to keep email/password login)
   - ❌ Disable **ALLOW_USER_SRP_AUTH** (optional, for SRP authentication)

### 5. Configure Lambda Triggers for Custom Auth (CRITICAL)

For phone number OTP login to work, you need to set up Lambda triggers:

1. Navigate to **User pool properties** tab
2. Under **Lambda triggers**, configure:

#### Create Lambda Functions:

**a) Define Auth Challenge Lambda**:
```python
def lambda_handler(event, context):
    if event['request']['session'] and len(event['request']['session']) == 0:
        # First attempt - send SMS
        event['response']['issueTokens'] = False
        event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
    elif event['request']['session'] and len(event['request']['session']) == 1:
        # Second attempt - verify OTP
        if event['request']['challengeAnswer'] == event['request']['privateChallengeParameters']['answer']:
            event['response']['issueTokens'] = True
        else:
            event['response']['issueTokens'] = False
            event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
    else:
        event['response']['issueTokens'] = False
    
    return event
```

**b) Create Auth Challenge Lambda**:
```python
import random

def lambda_handler(event, context):
    if event['request']['challengeName'] == 'CUSTOM_CHALLENGE':
        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        
        # Send OTP via SNS (Cognito will handle this automatically)
        event['response']['publicChallengeParameters'] = {}
        event['response']['privateChallengeParameters'] = {'answer': otp}
        event['response']['challengeMetadata'] = 'OTP_CHALLENGE'
    
    return event
```

**c) Verify Auth Challenge Response Lambda**:
```python
def lambda_handler(event, context):
    expected_answer = event['request']['privateChallengeParameters']['answer']
    user_answer = event['request']['challengeAnswer']
    
    event['response']['answerCorrect'] = (expected_answer == user_answer)
    
    return event
```

2. **Attach Lambda Functions to Cognito**:
   - **Define auth challenge**: Select your Define Auth Challenge Lambda
   - **Create auth challenge**: Select your Create Auth Challenge Lambda
   - **Verify auth challenge response**: Select your Verify Auth Challenge Lambda

### 6. Configure MFA Settings (Optional but Recommended)

1. Navigate to **Sign-in experience** tab
2. Under **Multi-factor authentication**:
   - Select **Optional** or **Required**
   - Enable **SMS message** as MFA method
   - Configure SMS message template

### 7. Environment Variables

Update your `.env` file with:

```env
AWS_COGNITO_REGION=us-east-1
AWS_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
AWS_COGNITO_CLIENT_ID=your_client_id
AWS_COGNITO_CLIENT_SECRET=your_client_secret
```

## API Endpoints

### Signup Flow

**1. Initiate Signup**
```bash
POST /auth/phone/signup
Content-Type: application/json

{
  "phone_number": "+919876543210",
  "name": "John Doe"
}

Response:
{
  "message": "OTP sent to phone number. Please verify to complete signup.",
  "phone_number": "+919876543210",
  "user_sub": "uuid-here"
}
```

**2. Verify Signup OTP**
```bash
POST /auth/phone/verify-signup
Content-Type: application/json

{
  "phone_number": "+919876543210",
  "otp_code": "123456"
}

Response:
{
  "message": "Phone number verified successfully. You can now login.",
  "phone_number": "+919876543210",
  "verified": true
}
```

### Login Flow

**1. Initiate Login**
```bash
POST /auth/phone/login
Content-Type: application/json

{
  "phone_number": "+919876543210"
}

Response:
{
  "message": "OTP sent to your phone number",
  "session": "session-token-here",
  "phone_number": "+919876543210"
}
```

**2. Verify Login OTP**
```bash
POST /auth/phone/login/verify
Content-Type: application/json

{
  "phone_number": "+919876543210",
  "session": "session-token-from-step-1",
  "otp_code": "123456"
}

Response:
{
  "access_token": "eyJraWQiOiI...",
  "id_token": "eyJraWQiOiI...",
  "refresh_token": "eyJjdHkiOiI...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

## Testing

### Test Phone Numbers (Sandbox Mode)

For testing without sending real SMS:

1. Go to **Messaging** tab in Cognito
2. Under **SMS**, enable **Sandbox mode**
3. Add test phone numbers with fixed OTP codes:
   - Phone: `+919999999999`
   - OTP: `123456`

### Using Real Phone Numbers

1. Ensure SNS is properly configured
2. Check SNS spending limits
3. Verify phone number is in E.164 format: `+[country_code][number]`
   - India: `+919876543210`
   - US: `+11234567890`

## Troubleshooting

### Issue: "CUSTOM_AUTH flow not enabled"
**Solution**: Enable `ALLOW_CUSTOM_AUTH` in App Client settings

### Issue: "SMS not being sent"
**Solution**: 
- Check IAM role permissions for SNS
- Verify SNS spending limit not exceeded
- Check CloudWatch logs for Lambda errors
- Ensure phone number is in E.164 format

### Issue: "Invalid session"
**Solution**: Session tokens expire quickly (3 minutes). User must verify OTP within this time.

### Issue: "CodeMismatchException"
**Solution**: 
- User entered wrong OTP
- OTP expired (typically 3 minutes)
- Request new OTP by calling login endpoint again

### Issue: "LimitExceededException"
**Solution**: 
- Too many attempts
- Wait before retrying
- Check Cognito rate limits

## Cost Considerations

### SNS SMS Pricing (as of 2024)
- **India**: ~$0.00645 per SMS
- **US**: ~$0.00645 per SMS
- **Other countries**: Varies by region

### Cognito Pricing
- **MAU (Monthly Active Users)**: 
  - First 50,000 MAUs: Free
  - Next 50,000 MAUs: $0.0055/MAU
  - Beyond 100,000: $0.0046/MAU

## Security Best Practices

1. **Rate Limiting**: Implement rate limiting on OTP endpoints to prevent abuse
2. **OTP Expiry**: OTPs expire in 3 minutes (Cognito default)
3. **Max Attempts**: Limit OTP verification attempts (3-5 attempts)
4. **Phone Verification**: Always verify phone number ownership
5. **HTTPS Only**: Always use HTTPS in production
6. **Token Storage**: Store tokens securely on client side
7. **Refresh Tokens**: Use refresh tokens to get new access tokens

## Production Checklist

- [ ] SNS configured with IAM role (not Cognito default)
- [ ] SNS spending limits set appropriately
- [ ] Lambda triggers configured and tested
- [ ] Test phone numbers removed from production
- [ ] Rate limiting implemented on endpoints
- [ ] Error handling and logging configured
- [ ] Phone number format validation (E.164)
- [ ] Token refresh flow implemented
- [ ] HTTPS enforced
- [ ] CloudWatch alarms set for errors and costs

## Additional Resources

- [AWS Cognito Custom Auth Flow](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow.html#amazon-cognito-user-pools-custom-authentication-flow)
- [SNS SMS Pricing](https://aws.amazon.com/sns/sms-pricing/)
- [Cognito Lambda Triggers](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools-working-with-aws-lambda-triggers.html)
