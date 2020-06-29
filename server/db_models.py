from peewee import Model, CharField, IntegerField, BooleanField
from config import SYSTEM_FOLDERS


def init_log_model(db):
    class BaseModel(Model):
        class Meta:
            database = db

    class LogMessage(BaseModel):
        text = CharField()
        created_at = IntegerField()

    if db.is_closed():
        db.connect()

    db.create_tables([LogMessage])

    return LogMessage


def init_sync_models(db):
    class BaseModel(Model):
        class Meta:
            database = db

    class Login(BaseModel):
        token = CharField(default='')
        token_expires = IntegerField(default=0)
        refresh_token = CharField(default='')
        type = CharField(default='OAuth')

    class Project(BaseModel):
        name = CharField()
        project_id = CharField(default='')
        root_asset_id = CharField(default='')
        team_id = CharField(default='')

        local_path = CharField(default='')
        local_size = IntegerField(default=0)
        frameio_size = IntegerField(default=0)

        sync = BooleanField(default=False)
        new_data = BooleanField(default=False)
        last_scan = CharField(default='2014-02-07T00:00:01.000000+00:00')
        deleted_from_frameio = BooleanField(default=False)
        db_delete_requested = BooleanField(default=False)

    class Asset(BaseModel):
        name = CharField()
        path = CharField()  # relative to project root
        is_file = BooleanField(default=False)
        asset_id = CharField(default='')
        parent_id = CharField(default='')
        project_id = CharField()
        original = CharField(default='')

        ignore = BooleanField(default=False)
        on_frameio = BooleanField(default=False)
        on_local_storage = BooleanField(default=False)
        local_xxhash = CharField(default='')
        frameio_xxhash = CharField(default='')

        uploaded_at = IntegerField(default=0)
        upload_verified = BooleanField(default=True)
        upload_retries = IntegerField(default=0)

    class IgnoreFolder(BaseModel):
        name = CharField()
        type = CharField()

    if db.is_closed():
        db.connect()

    db.create_tables([Project, Asset, Login, IgnoreFolder])

    config = Login.get_or_none()
    if config is None:
        Login.create()

    ignore = IgnoreFolder.get_or_none()
    if ignore is None:
        for folder in SYSTEM_FOLDERS:
            IgnoreFolder(name=folder, type='SYSTEM').save()

    return Login, Project, Asset, IgnoreFolder
