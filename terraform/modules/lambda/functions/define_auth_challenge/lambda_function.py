"""
Define Auth Challenge Lambda
Determines which challenge to present to the user during custom auth flow
"""

def lambda_handler(event, context):
    """
    Define the auth challenge based on the session
    """
    print(f"Define Auth Challenge Event: {event}")
    
    # Get the session
    session = event['request']['session']
    
    # If this is the first attempt, issue a custom challenge
    if len(session) == 0:
        event['response']['issueTokens'] = False
        event['response']['failAuthentication'] = False
        event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
    
    # If the user has answered the challenge correctly, issue tokens
    elif len(session) > 0 and session[-1]['challengeName'] == 'CUSTOM_CHALLENGE':
        if session[-1]['challengeResult']:
            event['response']['issueTokens'] = True
            event['response']['failAuthentication'] = False
        else:
            # User answered incorrectly, allow retry up to 3 attempts
            if len(session) >= 3:
                event['response']['issueTokens'] = False
                event['response']['failAuthentication'] = True
            else:
                event['response']['issueTokens'] = False
                event['response']['failAuthentication'] = False
                event['response']['challengeName'] = 'CUSTOM_CHALLENGE'
    
    print(f"Define Auth Challenge Response: {event['response']}")
    return event
