import mimetypes
import os
from threading import Thread
from time import sleep
from time import time
from datetime import datetime, timezone, timedelta

import requests
import xxhash
from peewee import SqliteDatabase

import config
from db_models import init_sync_models
from logger import logger
from main import authenticated_client


def xxhash_file(fname):
    """Calculate XXHash 64 of file and return it."""
    logger.info(
        'Calculating local hash of: {}'.format(os.path.basename(fname)))

    xx_hash = xxhash.xxh64()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            xx_hash.update(chunk)
    return xx_hash.hexdigest()


def folder_size(path):
    """Calculate total folder size, including the dirs size on file system."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
        for f in dirnames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)

    return total_size


def file_is_ready(file_abs_path):
    """Checks if a files is rendered/copied completely."""
    logger.info(
        'Checking if file is ready: {}'.format(
            os.path.basename(file_abs_path)))

    file_size = os.path.getsize(file_abs_path)

    if file_size == 0:
        return False

    sleep(config.NEW_FILE_DELTA_INTERVAL)
    if os.path.getsize(file_abs_path) != file_size:
        return False

    return True


class SyncLoop(Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.db = SqliteDatabase(os.path.join(config.DB_FOLDER, 'sync.db'),
                                 pragmas={'journal_mode': 'wal'})
        self.Project, self.Asset, self.IgnoreFolder = init_sync_models(
            self.db)[1:]

    def update_frameio_projects(self):
        """Get all projects from Frame.io and add new to DB.
        Check projects size (number of files+folders), and flag it as updated
        if size has changed since last scan.
        """
        logger.info('Scanning Frame.io for updates')

        projects = []
        try:
            for team in authenticated_client().get_all_teams():
                projects += authenticated_client().get_projects(team['id'])
        except (requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError):
            raise

        for project in projects:
            try:
                db_project = self.Project.get(
                    self.Project.project_id == project['id'])

                # Check if project has been renamed
                if db_project.name != project['name']:
                    db_project.name = project['name']
                    db_project.save()

                    logger.info(
                        'Renamed project {} to {}'.format(db_project.name,
                                                          project['name']))

                # Check size to see if new data has been added
                if db_project.sync:
                    new_frameio_size = int(project['file_count']) + int(
                        project['folder_count'])
                    if new_frameio_size > db_project.frameio_size:
                        db_project.frameio_size = new_frameio_size
                        db_project.new_data = True
                        db_project.save()

            except self.Project.DoesNotExist:
                self.Project(name=project['name'],
                             frameio_size=int(project['file_count']) + int(
                                 project['folder_count']),
                             project_id=project['id'],
                             root_asset_id=project['root_asset_id'],
                             team_id=project['team_id'],
                             new_data=True,
                             on_frameio=True).save()

        # Check if any projects have been deleted
        active_projects_ids = [project['id'] for project in projects]

        for db_project in self.Project.select().where(
                self.Project.deleted_from_frameio == False):
            if db_project.project_id not in active_projects_ids:
                db_project.deleted_from_frameio = True
                db_project.sync = False
                db_project.save()

                logger.info(
                    "Project {} has been deleted, "
                    "turning off sync.".format(db_project.name))

    def update_local_projects(self):
        """Get local folders size and flag project as updated if size
        has changed since last scan. If folder can't be found, turn off sync
        and delete project and corresponding assets from DB.
        """
        logger.info('Scanning local storage for updates')

        projects = self.Project.select().where(self.Project.sync == True)
        for project in projects:
            if os.path.isdir(project.local_path):
                # Check size to see if new data has been added
                local_size = folder_size(project.local_path)
                if project.local_size != local_size:
                    project.local_size = local_size
                    project.new_data = True
                    project.save()
            else:
                logger.info(
                    'Local folder for {} not found, turning off sync'.format(
                        project.name))

                self.delete_db_project(project)

    def update_frameio_assets(self, project, ignore_folders):
        """Fetch assets that've been added since last scan and add them to DB.

        :Args:
        project (DB Project)
        ignore_folders (List)
        """
        logger.info('Scanning Frame.io project {} for new assets'.format(
            project.name))

        # Always overscan by 10 minutes to help avoid missing assets.
        start_timestamp = (
                datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        try:
            account_id = authenticated_client().get_me()['account_id']
            new_assets = authenticated_client().get_assets_inserted_after(
                account_id, project.project_id, project.last_scan)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError):
            raise

        if len(new_assets) == 0:
            return

        new_folders = [a for a in new_assets if a['type'] == 'folder']
        new_files = [a for a in new_assets if a['type'] == 'file']

        added_files = 0
        added_folders = 0

        # Loop until we find correct folder order and all folders are added.
        # folder1/folder2/folder3
        found_folders = 0
        while found_folders != len(new_folders):
            for folder in new_folders:
                ignore = False

                # Folder is at root level.
                if folder['parent_id'] == project.root_asset_id:
                    parent_id = project.root_asset_id
                    parent_path = ''

                # Folder not at root, see if parent is in DB.
                # If not, skip and continue.
                else:
                    try:
                        parent = self.Asset.get(
                            self.Asset.asset_id == folder['parent_id'])

                        parent_id = parent.asset_id
                        parent_path = parent.path

                        if parent.ignore:
                            ignore = True

                    except self.Asset.DoesNotExist:
                        continue

                # Parent found in DB or folder is at root.
                # Test if folder already exists in DB, otherwise add it.
                folder_path = os.path.join(parent_path, folder['name'])
                try:
                    self.Asset.get(
                        (self.Asset.path == folder_path) &
                        (self.Asset.project_id == project.project_id))

                    # Already synced
                    found_folders += 1

                except self.Asset.DoesNotExist:
                    if folder['name'] in ignore_folders:
                        ignore = True

                    added_folders += 1
                    self.Asset(name=folder['name'],
                               project_id=project.project_id,
                               path=folder_path,
                               asset_id=folder['id'],
                               parent_id=parent_id,
                               ignore=ignore,
                               on_frameio=True).save()

                    found_folders += 1

        for file in new_files:
            ignore = False

            # File is at root level.
            if file['parent_id'] == project.root_asset_id:
                parent_id = project.root_asset_id
                parent_path = ''

            # Not at root, find parent in DB.
            else:
                parent = self.Asset.get(
                    self.Asset.asset_id == file['parent_id'])
                parent_id = parent.asset_id
                parent_path = parent.path

                if parent.ignore:
                    ignore = True

            # Parent found in DB or file is at root.
            # Test if file already exists in DB, otherwise add it.
            file_path = os.path.join(parent_path, file['name'])
            try:
                self.Asset.get(
                    (self.Asset.path == file_path) &
                    (self.Asset.project_id == project.project_id))

            # New file
            except self.Asset.DoesNotExist:
                added_files += 1
                self.Asset(name=file['name'],
                           project_id=project.project_id,
                           path=file_path,
                           is_file=True,
                           asset_id=file['id'],
                           parent_id=parent_id,
                           original=file['original'],
                           ignore=ignore,
                           on_frameio=True).save()

        if added_folders != 0:
            logger.info('Added {} folders'.format(added_folders))

        if added_files != 0:
            logger.info('Added {} files'.format(added_files))

        project.last_scan = start_timestamp
        project.save()

    def update_local_assets(self, project, ignore_folders):
        """Scans local storage for assets and creates new ones in DB.

        :Args:
        project (DB project)
        ignore_folders (List)
        """
        logger.info('Scanning local storage project {} for new assets'.format(
            project.name))

        abs_project_path = os.path.abspath(project.local_path)

        for root, dirs, files in os.walk(abs_project_path, topdown=True):
            dirs[:] = [d for d in dirs if
                       d not in ignore_folders and not d.startswith(".")]

            for name in files:
                if not name.startswith('.'):
                    path = os.path.relpath(
                        os.path.join(root, name), abs_project_path)

                    try:
                        db_asset = self.Asset.get(
                            self.Asset.project_id == project.project_id,
                            self.Asset.path == path)

                        # Already synced
                        if db_asset.on_local_storage is False:
                            logger.info(
                                '{} already synced'.format(db_asset.path))
                            db_asset.on_local_storage = True
                            db_asset.save()

                    # New file
                    except self.Asset.DoesNotExist:
                        if file_is_ready(os.path.join(root, name)):
                            logger.info(
                                'File ready: {}'.format(name))
                            self.Asset(name=name,
                                       project_id=project.project_id,
                                       path=path,
                                       is_file=True,
                                       on_local_storage=True,
                                       local_xxhash=xxhash_file(
                                           os.path.join(root, name))).save()
                        else:
                            # New file but not ready yet. Flag project as
                            # updated this file is retried
                            project.new_data = True
                            project.save()

            for name in dirs:
                path = os.path.relpath(os.path.join(root, name),
                                       abs_project_path)

                try:
                    db_asset = self.Asset.get(
                        self.Asset.project_id == project.project_id,
                        self.Asset.path == path)

                    # Already synced
                    if db_asset.on_local_storage is False:
                        logger.info(
                            '{} already synced'.format(db_asset.path))
                        db_asset.on_local_storage = True
                        db_asset.save()

                except self.Asset.DoesNotExist:
                    self.Asset(name=name,
                               project_id=project.project_id,
                               on_local_storage=True,
                               path=path).save()

    def download_new_assets(self, project):
        """Get new assets from DB and download them"""
        new_folders = self.Asset.select().where(
            (self.Asset.on_local_storage == False) &
            (self.Asset.is_file == False) &
            (self.Asset.project_id == project.project_id) &
            (self.Asset.ignore == False))

        new_files = self.Asset.select().where(
            (self.Asset.on_local_storage == False) &
            (self.Asset.is_file == True) &
            (self.Asset.project_id == project.project_id) &
            (self.Asset.ignore == False))

        if len(new_folders) == 0 and len(new_files) == 0:
            logger.info('Nothing to download')
            return

        for folder in new_folders:
            logger.info('Creating local folder: {}'.format(
                os.path.join(project.local_path, folder.path)))

            os.makedirs(os.path.join(
                project.local_path, folder.path),
                exist_ok=True)

            folder.on_local_storage = True
            folder.save()

        for file in new_files:
            logger.info('Downloading: {}'.format(file.name))
            download_folder = os.path.join(project.local_path,
                                           os.path.dirname(file.path))

            try:
                authenticated_client().download(
                    asset={"name": file.name, "original": file.original},
                    download_folder=download_folder)

            except FileExistsError:
                pass

            # Add local props to new file
            file.on_local_storage = True
            file.local_xxhash = xxhash_file(
                os.path.join(download_folder, file.name))
            file.save()

    @staticmethod
    def new_frameio_folder(name, parent_asset_id):
        """Create single folder on Frame.io"""
        logger.info('Creating Frame.io folder: {}'.format(name))

        asset = authenticated_client().create_asset(
            parent_asset_id=parent_asset_id,
            name=name,
            type="folder",
        )

        return asset['id']

    def create_frameio_folder_tree(self, project, new_folder_path):
        """Step up folder tree in DB to find the closest parent folder on
        Frame.io. Then creates new folders on Frame.io down to the
        new folder and save all new asset_ids to DB.

        :Args:
            project (Project): In what project to create
            new_folder (string): Path to folder to create
        """
        current_path = os.path.dirname(new_folder_path)
        while current_path != '':  # While not at root
            try:
                db_asset = self.Asset.get(
                    self.Asset.project_id == project.project_id,
                    self.Asset.path == current_path,
                    self.Asset.on_frameio == True)
                break
            except self.Asset.DoesNotExist:
                # Not found, continue up in tree
                current_path = os.path.dirname(current_path)

        # Parent folder was found
        try:
            parent_asset_id = db_asset.asset_id
            parent_path = db_asset.path

        # No parent folder found, root is closest
        except NameError:
            parent_asset_id = project.root_asset_id
            parent_path = ''

        new_tree = os.path.relpath(new_folder_path, parent_path)
        for folder in new_tree.split('/'):
            asset_id = self.new_frameio_folder(folder, parent_asset_id)

            path = os.path.join(parent_path, folder)
            asset = self.Asset.get(self.Asset.path == path,
                                   self.Asset.project_id == project.project_id)
            asset.asset_id = asset_id
            asset.on_frameio = True
            asset.save()

            parent_asset_id = asset_id
            parent_path = path

    @staticmethod
    def upload_asset(abs_path, parent_asset_id):
        """Upload single asset to Frame.io."""
        file_mime = mimetypes.guess_type(abs_path)[0]
        new_asset = authenticated_client().create_asset(
            parent_asset_id=parent_asset_id,
            name=os.path.basename(abs_path),
            type="file",
            filetype=file_mime,
            filesize=os.path.getsize(abs_path)
        )

        with open(abs_path, "rb") as ul_file:
            authenticated_client().upload(new_asset, ul_file)

        return new_asset

    def upload_new_assets(self, project):
        """Upload new local assets to Frame.io and save new asset ids to DB."""
        new_folders = self.Asset.select().where(
            (self.Asset.on_frameio == False) &
            (self.Asset.is_file == False) &
            (self.Asset.project_id == project.project_id))

        new_files = self.Asset.select().where(
            (self.Asset.on_frameio == False) &
            (self.Asset.is_file == True) &
            (self.Asset.project_id == project.project_id))

        if len(new_folders) == 0 and len(new_files) == 0:
            logger.info('Nothing to upload')
            return

        for folder in new_folders:
            self.create_frameio_folder_tree(project=project,
                                            new_folder_path=folder.path)

        for file in new_files:
            logger.info('Uploading asset: {}'.format(file.name))
            abs_path = os.path.abspath(
                os.path.join(project.local_path, file.path))

            if os.path.dirname(file.path) == '':
                parent_asset_id = project.root_asset_id
            else:
                parent_asset_id = self.Asset.get(
                    self.Asset.project_id == project.project_id,
                    self.Asset.path == os.path.dirname(
                        file.path)).asset_id

            new_asset = self.upload_asset(abs_path, parent_asset_id)
            logger.info('Upload done: {}'.format(new_asset['name']))

            file.asset_id = new_asset['id']
            file.original = new_asset['original']
            file.uploaded_at = int(time())
            file.on_frameio = True
            file.upload_verified = False
            file.save()

    def delete_and_reupload(self, project, asset):
        """Delete and re-upload asset to Frame.io. Max attempts: 3."""
        logger.info('Deleting and re-uploading: {}'.format(asset.name))

        if asset.upload_retries == 2:
            logger.info(
                'Asset already uploaded 3 times. Marking as successful anyway')
            asset.upload_verified = True
            asset.save()
            return

        authenticated_client().delete_asset(asset.asset_id)
        abs_path = os.path.abspath(
            os.path.join(project.local_path, asset.path))

        if os.path.dirname(asset.path) == '':
            parent_asset_id = project.root_asset_id
        else:
            parent_asset_id = self.Asset.get(
                self.Asset.project_id == project.project_id,
                self.Asset.path == os.path.dirname(
                    asset.path)).asset_id

        new_asset = self.upload_asset(abs_path, parent_asset_id)
        asset.asset_id = new_asset['id']
        asset.original = new_asset['original']
        asset.uploaded_at = int(time())
        asset.on_frameio = True
        asset.upload_verified = False
        asset.upload_retries += 1
        asset.save()

    def verify_new_uploads(self):
        """Get xxhash from Frame.io and compare it to local hash in DB.
        Call delete and re-upload if hashes don't match.
        """
        new_assets = self.Asset.select().where(
            (self.Asset.upload_verified == False))

        if len(new_assets) == 0:
            logger.info('Nothing to verify')

        for asset in new_assets:
            if int(time()) - asset.uploaded_at < 100:
                continue  # Giving Frame.io time to calculate hash.

            logger.info('New upload to verify: {}'.format(asset.name))

            project = self.Project.get(
                self.Project.project_id == asset.project_id)

            try:
                frameio_asset = authenticated_client().get_asset(
                    asset.asset_id)
            except requests.exceptions.HTTPError:
                # Asset no longer available on Frame.io to verify
                # Maybe sync client crashed when deleting and re-uploading
                # Delete from DB to restart sync
                project.new_data = True
                project.save()
                asset.delete_instance()
                return

            if frameio_asset.get('upload_completed_at') is None:
                logger.info('Upload failed')
                self.delete_and_reupload(project=project, asset=asset)

            else:
                try:
                    frameio_hash = frameio_asset['checksums']['xx_hash']
                    if frameio_hash != asset.local_xxhash:
                        logger.info('Hash mismatch')
                        self.delete_and_reupload(project=project, asset=asset)

                    else:
                        logger.info('Upload succeeded')
                        asset.frameio_xxhash = frameio_hash
                        asset.upload_verified = True
                        asset.save()

                except (KeyError, TypeError):
                    logger.info('No calculated checksum yet')

                    # Edge cases where Frame.io fails to calculate a checksum.
                    # Mark as successful anyway.
                    if (time() - asset.uploaded_at) > 1800:
                        logger.info(
                            """30 mins since upload and no checksum on 
                            Frame.io, marking as successful anyway""")
                        asset.upload_verified = True
                        asset.save()

    def delete_db_project(self, project):
        """Delete project and its associated assets from DB."""
        logger.info('Deleting project {} from DB.'.format(project.name))

        for asset in self.Asset.select().where(
                self.Asset.project_id == project.project_id):
            asset.delete_instance()

        project.delete_instance()

    def run(self):
        logger.info('Sync thread started')
        while True:
            if authenticated_client():
                try:
                    if self.db.is_closed():
                        self.db.connect()

                    self.update_frameio_projects()
                    self.update_local_projects()

                    updated_projects = self.Project.select().where(
                        (self.Project.new_data == True) &
                        (self.Project.sync == True))

                    for project in updated_projects:
                        logger.info('Updates in: {}'.format(project.name))

                        # Set project as DONE before asset scans so the below
                        # functions can revert to NOT DONE if they find
                        # assets that are new but not done
                        project.new_data = False
                        project.save()

                        ignore_folders = [folder.name for folder in
                                          self.IgnoreFolder.select()]

                        self.update_frameio_assets(
                            project=project,
                            ignore_folders=ignore_folders)

                        self.update_local_assets(
                            project=project,
                            ignore_folders=ignore_folders)

                        if config.SyncSetting.ASSETS_LOCAL_TO_FRAME:
                            self.upload_new_assets(project)
                        if config.SyncSetting.ASSETS_FRAMEIO_TO_LOCAL:
                            self.download_new_assets(project)

                    self.verify_new_uploads()

                    # Delete projects that have both been deleted from Frame.io
                    # and the user has requested it be deleted from DB.
                    for project in self.Project.select().where(
                            self.Project.db_delete_requested == True):
                        self.delete_db_project(project)

                    logger.info(
                        'Sleeping for {} secs'.format(config.SCAN_INTERVAL))
                    self.db.close()

                except (requests.exceptions.ConnectionError,
                        requests.exceptions.HTTPError):
                    # Might be temp bad internet.
                    logger.info('Could not connect, retrying in {}'.format(
                        config.SCAN_INTERVAL))

            sleep(config.SCAN_INTERVAL)
