import fnmatch
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from threading import Thread
from time import sleep, time

import requests
from dateutil import parser
from requests import auth

import config
from db_handler import db_queue
from frameioclient.utils import calculate_hash
from logger import logger
from main import authenticated_client


class SyncLoop(Thread):
    def __init__(self, db, project, asset, ignore_folder, **kwargs):
        super().__init__(**kwargs)
        self.daemon = True
        self.db = db
        self.Project = project
        self.Asset = asset
        self.IgnoreFolder = ignore_folder

    @staticmethod
    def wildcard_match(name, ignore_list):
        for ignore in ignore_list:
            if fnmatch.fnmatch(name, ignore):
                return True

        return False

    def update_projects(self):
        """Get all projects from Frame.io and add new to DB."""
        projects = []
        try:
            for team in authenticated_client().get_all_teams():
                # print(f"{team['name']}: {team['id']}")
                projects += authenticated_client().get_projects(team['id'])
        except (requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError):
            raise

        # try:
        #     projects += authenticated_client().get_shared_projects() # could take a while to run
        # except (requests.exceptions.ConnectionError,
        #         requests.exceptions.HTTPError):
        #     raise

        for project in projects:
            try:
                db_project = self.Project.get(
                    self.Project.project_id == project['id'])

                # Check if project has been renamed
                if db_project.name != project['name']:
                    db_project.name = project['name']
                    db_queue.put([db_project, 'save'])

                    logger.info(
                        'Renamed project {} to {}'.format(db_project.name,
                                                          project['name']))

            except self.Project.DoesNotExist:
                logger.info('New project found: {}'.format(project['name']))

                new_project = self.Project(name=project['name'],
                                           project_id=project['id'],
                                           root_asset_id=project['root_asset_id'],
                                           team_id=project['team_id'],
                                           on_frameio=True)
                db_queue.put([new_project, 'save'])

        # Check if any projects have been deleted
        active_projects = [project['id'] for project in projects]

        for db_project in self.Project.select().where(
                self.Project.deleted_from_frameio == False):
            if db_project.project_id not in active_projects:
                db_project.deleted_from_frameio = True
                db_project.sync = False
                db_queue.put([db_project, 'save'])

                logger.info(
                    "Project {} has been deleted, "
                    "turning off sync.".format(db_project.name))

    def calculate_missing_paths(self, project, parent_id, parent_path,
                                ignore_folders, ignore):
        """Recurse through DB and add missing paths and if folder should be
        ignored.
        """
        children = self.Asset.select().where(
            (self.Asset.project_id == project.project_id) &
            (self.Asset.is_file == False) &
            (self.Asset.parent_id == parent_id))

        for child in children:
            if child.name in ignore_folders or ignore or self.wildcard_match(
                    child.name, ignore_folders):
                ignore = True

            if child.path == '':
                child.path = os.path.join(parent_path, child.name)
                child.ignore = ignore
                db_queue.put([child, 'save'])
                logger.info('Added path to folder {}'.format(child.path))

            self.calculate_missing_paths(project, child.asset_id, child.path,
                                         ignore_folders, ignore)

    def update_frameio_assets(self, project, ignore_folders):
        """Fetch assets that've been added since last scan and add them to DB.

        :Args:
        project (DB Project)
        ignore_folders (List)
        """
        # Always overscan by 10 minutes to help avoid missing assets.
        new_scan_timestamp = (
                datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        try:
            account_id = authenticated_client().get_project(project.project_id)['root_asset']['account_id']
            updated_assets = authenticated_client().get_updated_assets(
                account_id, project.project_id, project.last_frameio_scan)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError):
            raise

        # Find assets not already in DB.
        new_assets = []
        for asset in updated_assets:
            try:
                self.Asset.get(self.Asset.asset_id == asset['id'])

            except self.Asset.DoesNotExist:
                new_assets.append(asset)

        new_folders = [a for a in new_assets if a['type'] == 'folder']
        new_folders.sort(key=lambda a: a['inserted_at'])  # Oldest first
        new_files = [a for a in new_assets if a['type'] == 'file']

        added_folders = 0
        added_files = 0
        duplicates_folders = 0
        duplicates_files = 0

        # Filter out duplicate folders with same name/path
        new_folders_filtered = []
        for folder in new_folders:
            if (folder['name'] + folder['parent_id']) not in [
                f['name'] + f['parent_id'] for f in new_folders_filtered]:
                new_folders_filtered.append(folder)

        for folder in new_folders_filtered:
            ignore = False
            path = ''

            if folder['name'] in ignore_folders or self.wildcard_match(
                    folder['name'], ignore_folders):
                ignore = True

            if folder['parent_id'] == project.root_asset_id:
                path = folder['name']

            else:
                try:
                    parent = self.Asset.get(
                        self.Asset.asset_id == folder['parent_id'])

                    if parent.path != '':
                        path = os.path.join(parent.path, folder['name'])

                        if parent.ignore:
                            ignore = True

                except self.Asset.DoesNotExist:
                    pass

            # If folder has the same path/name as an existing one, ignore it
            try:
                self.Asset.get(self.Asset.path == path,
                               self.Asset.project_id == project.project_id)
                ignore = True
                duplicates_folders += 1

            except self.Asset.DoesNotExist:
                pass

            new_asset = self.Asset(name=folder['name'],
                                   project_id=project.project_id,
                                   path=path,
                                   asset_id=folder['id'],
                                   parent_id=folder['parent_id'],
                                   ignore=ignore,
                                   on_frameio=True)
            db_queue.put([new_asset, 'save'])
            added_folders += 1

        # If folders are out of order from Frame.io we need to calc paths.
        if self.Asset.select().where(self.Asset.path == ''):
            self.calculate_missing_paths(project=project,
                                         parent_id=project.root_asset_id,
                                         parent_path='',
                                         ignore_folders=ignore_folders,
                                         ignore=False)

        for file in new_files:
            if file['upload_completed_at'] is not None:
                ignore = False
                if file['parent_id'] == project.root_asset_id:
                    parent_path = ''

                else:
                    try:
                        parent = self.Asset.get(
                            self.Asset.asset_id == file['parent_id'])

                        if parent.path == '':
                            logger.info(
                                "Parent to {} path is not set, retry".format(
                                    file['name']))
                            continue

                        parent_path = parent.path

                        if parent.ignore:
                            ignore = True

                    except self.Asset.DoesNotExist:
                        logger.info('Parent to {} not found, retry'.format(
                            file['name']))
                        continue

                # Only add files with unique path and name.
                asset_path = os.path.join(parent_path, file['name'])
                try:
                    self.Asset.get(self.Asset.path == asset_path,
                                   self.Asset.project_id == project.project_id)
                    duplicates_files += 1

                except self.Asset.DoesNotExist:
                    new_asset = self.Asset(name=file['name'],
                                           project_id=project.project_id,
                                           path=asset_path,
                                           is_file=True,
                                           asset_id=file['id'],
                                           parent_id=file['parent_id'],
                                           original=file['original'],
                                           ignore=ignore,
                                           on_frameio=True)
                    db_queue.put([new_asset, 'save'])
                added_files += 1

        if added_folders - duplicates_folders != 0:
            logger.info(
                'New folders on Frame.io for project {}'.format(project.name))
        if added_files - duplicates_files != 0:
            logger.info(
                'New files on Frame.io for project {}'.format(project.name))

        if len(new_files) == added_files:  # All done. Moving up timestamp.
            project.last_frameio_scan = new_scan_timestamp

        db_queue.put([project, 'save'])

    def update_local_assets(self, project, ignore_folders):
        """Scan local storage for assets and creates new ones in DB.

        :Args:
        project (DB project)
        ignore_folders (List)
        """
        abs_project_path = os.path.abspath(project.local_path)
        if not os.path.isdir(abs_project_path):
            logger.info(
                'Local folder for {} not found, turning off sync'.format(
                    project.name))
            self.delete_db_project(project)
            return

        new_scan_time = int(time()) - 500  # Overscan to avoid missing assets.
        all_assets_ready = True
        new_folders = False
        new_files = False

        for root, dirs, files in os.walk(abs_project_path, topdown=True):
            dirs[:] = [d for d in dirs if
                       d not in ignore_folders and not d.startswith(
                           ".") and not self.wildcard_match(d, ignore_folders)]

            for name in files:
                full_path = os.path.join(root, name)
                if not name.startswith('.'):
                    try:
                        create_time = os.path.getctime(full_path)
                    except FileNotFoundError:
                        all_assets_ready = False
                        continue

                    # Add new file criteria
                    # - Created since last complete scan (all_assets_ready)
                    # - Not changed in the last 60 secs
                    # - Size not 0
                    if create_time > project.last_local_scan:
                        if (time() - create_time) < 60 or os.path.getsize(
                                full_path) == 0:
                            all_assets_ready = False
                            continue

                        path = os.path.relpath(full_path, abs_project_path)

                        try:
                            db_asset = self.Asset.get(
                                self.Asset.project_id == project.project_id,
                                self.Asset.path == path)

                            # Already synced
                            if db_asset.on_local_storage is False:
                                db_asset.on_local_storage = True
                                db_queue.put([db_asset, 'save'])

                        # New file
                        except self.Asset.DoesNotExist:
                            try:
                                file_hash = calculate_hash(full_path)
                            except FileNotFoundError:
                                all_assets_ready = False
                                continue

                            new_files = True
                            new_asset = self.Asset(name=name,
                                                   project_id=project.project_id,
                                                   path=path,
                                                   is_file=True,
                                                   on_local_storage=True,
                                                   local_xxhash=file_hash)
                            db_queue.put([new_asset, 'save'])

            for name in dirs:
                full_path = os.path.join(root, name)
                try:
                    create_time = os.path.getctime(full_path)
                except FileNotFoundError:
                    all_assets_ready = False
                    continue

                if create_time > project.last_local_scan:
                    path = os.path.relpath(full_path, abs_project_path)

                    try:
                        db_asset = self.Asset.get(
                            self.Asset.project_id == project.project_id,
                            self.Asset.path == path)

                        # Already synced
                        if db_asset.on_local_storage is False:
                            db_asset.on_local_storage = True
                            db_queue.put([db_asset, 'save'])

                    except self.Asset.DoesNotExist:
                        new_folders = True
                        new_asset = self.Asset(name=name,
                                               project_id=project.project_id,
                                               on_local_storage=True,
                                               path=path)
                        db_queue.put([new_asset, 'save'])

        if all_assets_ready:
            project.last_local_scan = new_scan_time
            db_queue.put([project, 'save'])

        if new_folders:
            logger.info(
                'New local folders for project {}'.format(project.name))
        if new_files:
            logger.info(
                'New local files for project {}'.format(project.name))

    def download_new_assets(self, project):
        """Get new assets from DB and download them"""
        new_folders = self.Asset.select().where(
            (self.Asset.on_local_storage == False) &
            (self.Asset.is_file == False) &
            (self.Asset.project_id == project.project_id) &
            (self.Asset.ignore == False) &
            (self.Asset.path != ''))

        new_files = self.Asset.select().where(
            (self.Asset.on_local_storage == False) &
            (self.Asset.is_file == True) &
            (self.Asset.project_id == project.project_id) &
            (self.Asset.ignore == False))

        if len(new_folders) == 0 and len(new_files) == 0:
            return

        for folder in new_folders:
            logger.info('Creating local folder: {}'.format(
                os.path.join(project.local_path, folder.path)))

            os.makedirs(os.path.join(
                project.local_path, folder.path),
                exist_ok=True)

            folder.on_local_storage = True
            db_queue.put([folder, 'save'])

        for file in new_files:
            try:
                asset = authenticated_client().get_asset(file.asset_id)
            except requests.exceptions.HTTPError:
                logger.info('File removed from Frame.io')
                db_queue.put(file, 'delete')
                continue

            if asset['checksums'] is None:
                logger.info('No checksum for {}'.format(file.name))

                # Allow Frame.io some time to calculate hash, retry next loop
                asset_uploaded_epoch = parser.parse(
                    asset['upload_completed_at']).timestamp()
                if time() - asset_uploaded_epoch < 300:
                    logger.info('Waiting for checksum'.format(file.name))
                    continue

            download_folder = os.path.join(project.local_path,
                                           os.path.dirname(file.path))

            if os.path.isdir(download_folder):
                logger.info('Downloading: {}'.format(file.path))

                try:
                    authenticated_client().download(asset,
                                                    download_folder=download_folder,
                                                    replace=False)

                except FileExistsError:
                    logger.info('{} already exists.'.format(file.path))

                # Add local props to new file
                file.on_local_storage = True
                db_queue.put([file, 'save'])
            else:
                logger.info('Download folder not found: {}'.format(file.path))
                db_queue.put([file, 'delete'])

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
            db_queue.put([asset, 'save'])

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
            return

        for folder in new_folders:
            if not os.path.isdir(
                    os.path.join(project.local_path, folder.path)):
                logger.info("Can't find {}, skipping.".format(folder.name))
                db_queue.put([folder, 'delete'])
                continue

            self.create_frameio_folder_tree(project=project,
                                            new_folder_path=folder.path)

        for file in new_files:
            if not os.path.isfile(os.path.join(project.local_path, file.path)):
                logger.info("Can't find {}".format(file.name))
                db_queue.put([file, 'delete'])
                continue

            logger.info('Uploading asset: {}'.format(file.path))
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
            logger.info('Upload done')

            file.asset_id = new_asset['id']
            file.original = new_asset['original']
            file.uploaded_at = int(time())
            file.on_frameio = True
            file.upload_verified = False
            db_queue.put([file, 'save'])

    def delete_and_reupload(self, project, asset):
        """Delete and re-upload asset to Frame.io. Max attempts: 3."""
        logger.info('Deleting and re-uploading: {}'.format(asset.name))

        if asset.upload_retries == 2:
            logger.info(
                'Asset already uploaded 3 times. Marking as successful anyway')
            asset.upload_verified = True
            db_queue.put([asset, 'save'])
            return

        try:
            authenticated_client().delete_asset(asset.asset_id)
        except requests.exceptions.HTTPError:  # Deleted by user already.
            pass

        abs_path = os.path.abspath(
            os.path.join(project.local_path, asset.path))

        if not os.path.isfile(abs_path):
            logger.info('{} not found'.format(asset.name))
            db_queue.put([asset, 'delete'])
            return

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
        db_queue.put([asset, 'save'])

    def verify_new_uploads(self):
        """Get xxhash from Frame.io and compare it to local hash in DB.
        Call delete and re-upload if hashes don't match.
        """
        new_assets = self.Asset.select().where(
            (self.Asset.upload_verified == False))

        if len(new_assets) == 0:
            return

        for asset in new_assets:
            if int(time()) - asset.uploaded_at < 100:
                continue  # Giving Frame.io time to calculate hash.

            logger.info('New upload to verify: {}'.format(asset.path))

            project = self.Project.get(
                self.Project.project_id == asset.project_id)

            try:
                frameio_asset = authenticated_client().get_asset(
                    asset.asset_id)
            except requests.exceptions.HTTPError:
                logger.info('Asset deleted from Frame.io, skipping')
                asset.upload_verified = True
                db_queue.put([asset, 'save'])
                continue

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
                        db_queue.put([asset, 'save'])

                except (KeyError, TypeError):
                    logger.info('No calculated checksum yet')

                    # Edge cases where Frame.io fails to calculate a checksum.
                    # Mark as successful anyway.
                    if (time() - asset.uploaded_at) > 1800:
                        logger.info(
                            """30 mins since upload and no checksum on 
                            Frame.io, marking as successful anyway""")
                        asset.upload_verified = True
                        db_queue.put([asset, 'save'])

    def delete_db_project(self, project):
        """Delete project and its associated assets from DB."""
        logger.info('Deleting project {} from DB.'.format(project.name))

        for asset in self.Asset.select().where(
                self.Asset.project_id == project.project_id):
            db_queue.put([asset, 'delete'])

        db_queue.put([project, 'delete'])

    def delete_assets_from_db(self, project):
        """Delete all assets from DB."""
        for asset in self.Asset.select().where(
                self.Asset.project_id == project.project_id):
            db_queue.put([asset, 'delete'])

    def remove_ignore_flag(self, assets, ignore_folders):
        for asset in assets:
            if asset.is_file:
                asset.ignore = False
                db_queue.put([asset, 'save'])

            if not asset.is_file:
                if asset.name not in ignore_folders and not self.wildcard_match(
                        asset.name, ignore_folders):
                    asset.ignore = False
                    db_queue.put([asset, 'save'])
                    children = self.Asset.select().where(
                        self.Asset.parent_id == asset.asset_id)
                    self.remove_ignore_flag(children, ignore_folders)

    def update_ignored_assets(self):
        """Find changes to ignore folders and un-flag blocked assets.

        Frame.io assets are added to DB even if they match an ignore folder.
        Remove the ignore flag, and download_new_assets will pick them up.

        Local assets are not added to DB if they match an ignore folder, just
        skipped. Reset last_scan will add/upload them.
        """
        removed_ignore_folders = self.IgnoreFolder.select().where(
            self.IgnoreFolder.removed == True)

        active_ignore_folders = [folder.name for folder in
                                 self.IgnoreFolder.select().where(
                                     self.IgnoreFolder.removed == False)]

        all_blocked_folders = self.Asset.select().where(
            (self.Asset.ignore == True) &
            (self.Asset.is_file == False))

        for ignore_folder in removed_ignore_folders:
            logger.info('Removing ignore folder {}'.format(ignore_folder.name))

            blocked_folders = [f for f in all_blocked_folders if
                               f.name == ignore_folder.name or self.wildcard_match(
                                   f.name, [ignore_folder.name])]

            self.remove_ignore_flag(blocked_folders, active_ignore_folders)
            db_queue.put([ignore_folder, 'delete'])

        for project in self.Project.select():  # Trigger re-scan of all
            project.last_local_scan = 0
            db_queue.put([project, 'save'])

    def run(self):
        while True:
            if authenticated_client():
                try:
                    logger.info('Checking for updates')
                    self.update_projects()

                    ignore_folders = [folder.name for folder in
                                      self.IgnoreFolder.select().where(
                                          self.IgnoreFolder.removed == False)]

                    for project in self.Project.select().where(
                            self.Project.sync == True):
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

                except (requests.exceptions.ConnectionError,
                        requests.exceptions.HTTPError):
                    logger.info('Could not connect, retrying in {}'.format(
                        config.SCAN_INTERVAL))

                # Delete project from DB if requested by user.
                for project in self.Project.select().where(
                        self.Project.db_delete_requested == True):
                    self.delete_db_project(project)

                # Delete assets to redo sync from scratch if path has been changed.
                for project in self.Project.select().where(
                        self.Project.local_path_changed == True):
                    logger.info('Path changed, deleting and recreating assets in db')

                    self.delete_assets_from_db(project)
                    project.local_path_changed = False
                    project.last_local_scan = 0
                    project.last_frameio_scan = '2014-02-07T00:00:01.000000+00:00'
                    db_queue.put([project, 'save'])

                # Updated ignored assets if an ignore folder has been removed.
                if self.IgnoreFolder.select().where(
                        self.IgnoreFolder.removed == True):
                    self.update_ignored_assets()

                self.db.close()
            sleep(config.SCAN_INTERVAL)
