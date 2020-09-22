"""
Utility functions related to authentication.
"""
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

import google_auth_oauthlib.flow
from google.oauth2 import id_token
from google.auth.transport import requests
from google.oauth2.credentials import Credentials

import json
import logging

from seqr.models import AnvilUser
from seqr.views.utils.json_utils import create_json_response
from seqr.views.utils.terra_api_utils import AnvilSession, scopes

CLIENT_SECRETS_FILE = "client_secret.json"

logger = logging.getLogger(__name__)


@csrf_exempt
def login_view(request):
    request_json = json.loads(request.body)
    if not request_json.get('email'):
        return create_json_response({}, status=400, reason='Email is required')
    if not request_json.get('password'):
        return create_json_response({}, status=400, reason='Password is required')

    users = User.objects.filter(email__iexact=request_json['email'])
    if users.count() != 1:
        return create_json_response({}, status=401, reason='Invalid credentials')

    u = authenticate(username=users.first().username, password=request_json['password'])
    if not u:
        return create_json_response({}, status=401, reason='Invalid credentials')

    request.session['anvil'] = None

    login(request, u)

    return create_json_response({'success': True})

@csrf_exempt
def login_google(request):
  # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=scopes)

  # The URI created here must exactly match one of the authorized redirect URIs
  # for the OAuth 2.0 client, which you configured in the API Console. If this
  # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
  # error.
  flow.redirect_uri = 'http://localhost:3000/oauth2callback'

  authorization_url, state = flow.authorization_url(
      # Enable offline access so that you can refresh an access token without
      # re-prompting the user for permission. Recommended for web server apps.
      access_type='offline',
      # Enable incremental authorization. Recommended as a best practice.
      include_granted_scopes='true')

  # Store the state so the callback can verify the auth server response.
  request.session['state'] = state

  # Return the url to be sent for the Google Auth server by the the front end
  return create_json_response({'data': authorization_url})

@csrf_exempt
def login_oauth2callback(request):
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = request.session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes = scopes, state = state)
    flow.redirect_uri = 'http://localhost:3000/oauth2callback'

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = request.body.decode('utf-8')
    flow.fetch_token(authorization_response = authorization_response)

    token = flow.credentials.id_token

    try:
        # Decode the id token (It is a JWT token actually) to get user ID info
        idinfo = id_token.verify_oauth2_token(token, requests.Request())
    except ValueError as ve:
        return create_json_response({}, status=401, reason=str(ve))

    credentials = Credentials(**credentials_to_dict(flow.credentials))
    session = AnvilSession(credentials = credentials, scopes = scopes)
    try:
        _ = session.get_anvil_profile()
    except Exception as ee:
        return create_json_response({}, status=400, reason='Google account must be registered on AnVIL first. \
        Please open https://anvil.terra.bio and sign in with Google to register your account. AnVIL responses: {}'
                                    .format(str(ee)))

    # To be updated to use user's Google ID to look for the user record in the model
    anvil_users = AnvilUser.objects.filter(anvil_user_name__iexact = idinfo['email'])
    if len(anvil_users) > 0: # Registered user
        user = anvil_users.first().user
    else:
        users = User.objects.filter(email__iexact = idinfo['email'])
        if len(users) == 0:
            return create_json_response({}, status=401, reason="User {} doesn't exist.".format(idinfo['email']))
        user = users.first()
        anvil_user = AnvilUser.create(user, idinfo['email'])
        anvil_user.save()

    # A temporary solution for Django authenticating the user without a password
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    request.session['anvil'] = session
    login(request, user)

    return create_json_response({'success': True})


def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}


def logout_view(request):
    logout(request)
    return redirect('/login')


def login_required_error(request):
    """Returns an HttpResponse with a 401 UNAUTHORIZED error message.

    This is used to redirect AJAX HTTP handlers to the login page.
    """
    assert not request.user.is_authenticated()

    return create_json_response({}, status=401, reason="login required")
