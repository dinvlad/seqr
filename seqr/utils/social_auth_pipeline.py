import logging

from django.shortcuts import redirect

from seqr.views.utils.terra_api_utils import anvil_call, TerraNotFoundException

logger = logging.getLogger(__name__)


def validate_anvil_registration(backend, response, *args, **kwargs):
    if backend.name == 'google-oauth2':
        try:
            anvil_call('get', 'register', response['access_token'])
        except TerraNotFoundException as et:
            logger.warning('User {} is trying to login without registration on AnVIL. {}'.format(response['email'], str(et)))
            return redirect('/login?anvilLoginFailed=true')


def validate_user_exist(backend, response, user=None, *args, **kwargs):
    if not user:
        logger.warning('Google user {} is trying to login without an existing seqr account ({}).'
                       .format(response['email'], backend.name))
        return redirect('/login?googleLoginFailed=true')


def log_signed_in(backend, response, is_new=False, *args, **kwargs):
    logger.info('Logged in {} ({})'.format(response['email'], backend.name))
    if is_new:
        logger.info('Created user {} ({})'.format(response['email'], backend.name))
