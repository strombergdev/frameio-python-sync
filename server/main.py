import os
import config
import frameioclient
from flask import Flask, jsonify, request, Response
from flask_cors import CORS, cross_origin
import requests
import requests.auth
import sync
from db_models import init_sync_models, init_log_model
from peewee import SqliteDatabase
from time import time
from logger import logger, handle_exception, PurgeOldLogMessages
import sys
import threading

app = Flask(__name__, static_url_path='', static_folder='client_dist')
CORS(app, resources={r'/*': {'origins': '*'}})

AUTHORIZE_URL = "https://applications.frame.io/oauth2/auth"
TOKEN_URL = "https://applications.frame.io/oauth2/token"

sync_db = SqliteDatabase(os.path.join(config.DB_FOLDER, 'sync.db'),
                         pragmas={'journal_mode': 'wal'})
Login, Project, Asset, IgnoreFolder = init_sync_models(sync_db)

log_db = SqliteDatabase(os.path.join(config.DB_FOLDER, 'log.db'),
                        pragmas={'journal_mode': 'wal'})
LogMessage = init_log_model(log_db)

sys.excepthook = handle_exception


def setup_thread_excepthook():
    """Workaround for `sys.excepthook` thread bug from:
    http://bugs.python.org/issue1230540

    Call once from the main thread before creating any threads.
    """

    init_original = threading.Thread.__init__

    def init(self, *args, **kwargs):

        init_original(self, *args, **kwargs)
        run_original = self.run

        def run_with_except_hook(*args2, **kwargs2):
            try:
                run_original(*args2, **kwargs2)
            except Exception:  # skipcq: PYL-W0703
                sys.excepthook(*sys.exc_info())

        self.run = run_with_except_hook

    threading.Thread.__init__ = init


def authenticated_client():
    """Return authenticated frame.io client either from cache or refresh"""
    if config.client_expires == 'NEVER':
        return config.authenticated_client
    if config.client_expires > time():
        return config.authenticated_client

    login = Login.select().limit(1).get()
    if login.token == '':  # Not logged in
        logger.info('Not logged in')
        sync_db.close()
        return False

    if login.type == 'DEVTOKEN':
        logger.info('Dev token login found')
        config.authenticated_client = frameioclient.FrameioClient(login.token)
        config.client_expires = 'NEVER'

        sync_db.close()
        return config.authenticated_client

    logger.info('Refreshing OAuth token')
    tokens = refresh_token(login.refresh_token)
    if tokens:
        tokens['type'] = 'OAUTH'
        save_tokens(tokens)
        token = tokens['access_token']
        config.authenticated_client = frameioclient.FrameioClient(token)
        config.client_expires = time() + 3300  # 5min padding for safety

    else:
        # Token might be too old, delete it to force use to re-auth
        logger.info("Couldn't refresh token, signing out")

        login = Login.select().limit(1).get()
        login.token = ''
        login.save()
        return False

    if not sync_db.is_closed():
        sync_db.close()

    return config.authenticated_client


def save_tokens(tokens):
    """Save tokens to DB."""
    login = Login.select().limit(1).get()

    login.token = tokens['access_token']
    login.refresh_token = tokens['refresh_token']
    login.type = tokens['type']
    if tokens['type'] == 'DEVTOKEN':
        login.token_expires = 'NEVER'
    else:
        login.token_expires = time() + 3300  # 5min padding for safety

    login.save()
    sync_db.close()


def refresh_token(token):
    """Refreshes token and returns new token/refresh pair."""
    post_data = {
        "grant_type": "refresh_token",
        "scope": config.SCOPES,
        "refresh_token": token,
        "client_id": config.CLIENT_ID
    }

    response = requests.post(TOKEN_URL, data=post_data)
    if response.status_code == 200:
        return response.json()
    return False


@app.route('/api/loginstatus', methods=['GET'])
def login_status():
    """Check Frame.io login status and return it."""
    if authenticated_client():
        return jsonify(logged_in=True)
    return jsonify(logged_in=False)


@app.route('/api/logindata', methods=['GET'])
def login_data():
    """Return parameters needed to begin OAuth login."""
    return jsonify(client_id=config.CLIENT_ID, scopes=config.SCOPES,
                   redirect_url=config.REDIRECT_URL)


@app.route('/api/devtokenlogin', methods=['POST'])
@cross_origin(headers=['Content-Type'])
def devtoken_login():
    """Login with dev token."""
    req = request.get_json()
    token = req['token']
    tokens = {'access_token': token,
              'refresh_token': 'None',
              'type': 'DEVTOKEN'}

    save_tokens(tokens)
    config.authenticated_client = frameioclient.FrameioClient(
        tokens['access_token'])
    config.client_expires = 'NEVER'

    logger.info('Logged in with dev token')
    return Response(status=200)


@app.route('/api/tokenexchange', methods=['POST'])
@cross_origin(headers=['Content-Type'])
def token_exchange():
    """Exchange code for token and save it to DB."""
    req = request.get_json()
    code = req['code']
    state = req['state']

    post_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.REDIRECT_URL,
        "state": state,
        "scope": config.SCOPES,
        "client_id": config.CLIENT_ID
    }

    response = requests.post(TOKEN_URL, data=post_data)
    tokens = response.json()
    tokens['type'] = 'OAUTH'
    save_tokens(tokens)
    config.authenticated_client = frameioclient.FrameioClient(
        tokens['access_token'])
    config.client_expires = time() + 3300  # 5min padding for safety

    logger.info('Logged in with OAuth')
    return Response(status=200)


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout of Frame.io and clear database."""
    config.authenticated_client = None
    config.client_expires = 0

    login = Login.select().limit(1).get()
    login.delete_instance()
    Login.create()  # Default row
    for asset in Asset.select():
        asset.delete_instance()
    for project in Project.select():
        project.delete_instance()

    sync_db.close()
    return Response(status=200)


@app.route('/api/teams', methods=['GET'])
def get_teams():
    """Get users teams from Frame.io."""
    if authenticated_client():
        return jsonify(authenticated_client().get_all_teams())
    return jsonify([])


@app.route('/api/<team_id>/projects', methods=['GET'])
def all_projects(team_id):
    """Get projects from DB and return them."""
    project_list = []
    projects = Project.select().where(Project.team_id == team_id)

    for project in projects:
        if project.local_path == '':
            project_path = 'Not set'
        else:
            project_path = project.local_path

        project_list.append({
            'id': project.project_id,
            'name': project.name,
            'sync': project.sync,
            'local_path': project_path,
            'deleted': project.deleted_from_frameio,
            'db_delete_requested': project.db_delete_requested})

    sync_db.close()
    return jsonify(project_list)


@cross_origin(headers=['Content-Type'])
@app.route('/api/projects/<project_id>', methods=['PUT', 'POST'])
def update_project(project_id):
    """Update selected project in DB."""
    req = request.get_json()
    project = Project.get(Project.project_id == project_id)

    if req.get('sync') is not None:
        if req['sync'] is False:
            logger.info('Sync changed to FALSE for {}'.format(project.name))
            project.sync = False
            project.save()
        else:
            logger.info('Sync changed to TRUE for {}'.format(project.name))
            project.sync = True
            project.save()

        sync_db.close()
        return Response(status=200)

    if req.get('local_path') is not None:
        abs_path = os.path.abspath(req['local_path'])

        if os.access(abs_path, os.W_OK):
            if req.get('sub_folder') != "":
                os.makedirs(os.path.join(
                    abs_path, req.get('sub_folder')), exist_ok=True)
                project.local_path = os.path.join(abs_path,
                                                  req.get('sub_folder'))
            else:
                project.local_path = abs_path

            logger.info(
                'Local path change to {} for {}'.format(project.local_path,
                                                        project.name))
            project.save()
            sync_db.close()
            return Response(status=200)

        return Response('Invalid path', status=400)


@app.route('/api/<project_id>/remove', methods=['POST'])
def remove_project(project_id):
    """Flag project so sync thread removes it and all its assets from DB."""
    try:
        project = Project.get(Project.project_id == project_id)
        project.db_delete_requested = True
        project.save()

        logger.info(
            'Project {} requested to be deleted from DB'.format(project.name))
        sync_db.close()
        return Response(status=200)

    except Project.DoesNotExist:
        return Response('Bad request', status=400)


@app.route('/api/folders', methods=['POST'])
def get_folders():
    """Get sub-folders in path and return them."""
    req = request.get_json()
    current_path = os.path.abspath(req['path'])

    ignore_folders = [folder.name for folder in IgnoreFolder.select().where(
        IgnoreFolder.type == 'SYSTEM')]

    folders = [f for f in os.listdir(current_path) if
               os.path.isdir(os.path.join(current_path, f)) and
               f not in ignore_folders and not f.startswith(".")]

    sync_db.close()
    return jsonify([os.path.join(current_path, f) for f in folders])


@app.route('/api/ignorefolders', methods=['GET', 'PUT', 'DELETE'])
def update_ignore_folders():
    """Get sub-folders in path and return them."""
    if request.method == 'GET':
        ignore_folders = [{"name": folder.name} for folder in
                          IgnoreFolder.select().where(
                              (IgnoreFolder.type == 'USER') &
                              (IgnoreFolder.removed == False))]
        sync_db.close()
        return jsonify(ignore_folders)

    if request.method == 'PUT':
        folder = request.get_json()['folder']
        IgnoreFolder(name=folder, type='USER').save()

        sync_db.close()
        return Response(status=200)

    if request.method == 'DELETE':
        # Flag as removed so sync loop updates all assets blocked by it.
        folder = request.get_json()['folder']

        db_folder = IgnoreFolder.get((IgnoreFolder.type == 'USER') & (
                IgnoreFolder.name == folder))

        db_folder.removed = True
        db_folder.save()

        sync_db.close()
        return Response(status=200)

    return Response('Bad request', status=400)


@app.route('/api/log', methods=['GET'])
def latest_log_messages():
    messages = [{"text": log.text, "created_at": log.created_at} for log in
                LogMessage.select().order_by(
                    LogMessage.created_at.desc()).limit(500)]

    messages.sort(key=lambda m: m['created_at'])
    messages[:] = [m['text'] for m in messages]
    log_db.close()

    return jsonify(messages)


@app.route("/")
def home():
    """Used if you want to serve both server and client from this web server.
    Run 'make buildweb' in project root first.
    """
    return app.send_static_file('index.html')


if __name__ == '__main__':
    authenticated_client()  # Trigger token refresh

    # Start logging cleanup thread
    setup_thread_excepthook()
    purge = PurgeOldLogMessages()
    purge.start()

    # Start sync thread
    loop = sync.SyncLoop()
    loop.start()

    app.run(port=5111)
