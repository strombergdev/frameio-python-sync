import sys
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from .download import FrameioDownloader

if sys.version_info.major >= 3:
  from .next_uploader import FrameioUploader
else:
  from .py2_uploader import FrameioUploader


class PaginatedResponse(object):
  def __init__(self, results=[], limit=None, page_size=0, total=0,
               total_pages=0, endpoint=None, method=None, payload={},
               client=None):
    self.results = results

    self.limit = limit
    self.page_size = int(page_size)
    self.total = int(total)
    self.total_pages = int(total_pages)

    self.endpoint = endpoint
    self.method = method
    self.payload = payload
    self.client = client

    self.asset_index = 0   # Index on current page
    self.returned = 0      # Total returned count
    self.current_page = 1

  def __iter__(self):
    return self

  def __next__(self):
    # Reset if we've reached end
    if self.returned == self.limit or self.returned == self.total:
      self.asset_index = 0
      self.returned = 0
      self.current_page = 1

      self.results = self.client.get_specific_page(
        self.method, self.endpoint, self.payload, page=1).results
      raise StopIteration

    if self.limit is None or self.returned < self.limit:
      if self.asset_index < self.page_size and self.returned < self.total:
        self.asset_index += 1
        self.returned += 1
        try:
          return self.results[self.asset_index - 1]
        except IndexError:
          raise StopIteration

      if self.current_page < self.total_pages:
        self.current_page += 1
        self.asset_index = 1
        self.returned += 1

        self.results = self.client.get_specific_page(
          self.method, self.endpoint, self.payload, self.current_page).results

        return self.results[self.asset_index - 1]

    raise StopIteration

  def next(self):  # Python 2
    return self.__next__()

  def __len__(self):
    if self.limit and self.limit < self.total:
      return self.limit

    return self.total


class FrameioClient(object):
  def __init__(self, token, host='https://api.frame.io'):
    self.token = token
    self.host = host
    self.retry_strategy = Retry(
      total=3,
      backoff_factor=1,
      status_forcelist=[429],
      method_whitelist=["POST", "OPTIONS", "GET"]
    )
    self.client_version = '3.6.8'

  def _get_version(self):
    try:
      from importlib import metadata
    except ImportError:
      # Running on pre-3.8 Python; use importlib-metadata package
      import importlib_metadata as metadata

    return metadata.version('frameioclient')

  def _api_call(self, method, endpoint, payload={}, limit=None):
    url = '{}/v2{}'.format(self.host, endpoint)

    headers = {
      'Authorization': 'Bearer {}'.format(self.token),
      'x-frameio-client': 'python/{}'.format(self.client_version)
    }

    adapter = HTTPAdapter(max_retries=self.retry_strategy)

    http = requests.Session()
    http.mount("https://", adapter)

    r = http.request(
      method,
      url,
      json=payload,
      headers=headers,
    )

    if r.ok:
      if r.headers.get('page-number'):
        if int(r.headers.get('total-pages')) > 1:
          return PaginatedResponse(
            results=r.json(),
            limit=limit,
            page_size=r.headers['per-page'],
            total_pages=r.headers['total-pages'],
            total=r.headers['total'],
            endpoint=endpoint,
            method=method,
            payload=payload,
            client=self
          )
      if isinstance(r.json(), list):
        return r.json()[:limit]
      return r.json()

    return r.raise_for_status()

  def get_specific_page(self, method, endpoint, payload, page):
    """
    Gets a specific page for that endpoint, used by Pagination Class

    :Args:
      method (string): 'get', 'post'
      endpoint (string): endpoint ('/accounts/<ACCOUNT_ID>/teams')
      payload (dict): Request payload
      page (int): What page to get
    """
    if method == 'get':
      endpoint = '{}?page={}'.format(endpoint, page)
      return self._api_call(method, endpoint)

    if method == 'post':
      payload['page'] = page
      return self._api_call(method, endpoint, payload=payload)

  def get_me(self):
    """
    Get the current user.
    """
    return self._api_call('get', '/me')

  def get_teams(self, account_id, **kwargs):
    """
    Get teams owned by the account. 
    (To return all teams, use get_all_teams())
    
    :Args:
      account_id (string): The account id.
    """
    endpoint = '/accounts/{}/teams'.format(account_id)
    return self._api_call('get', endpoint, kwargs)
  
  def get_team(self, team_id):
    """
    Get's a team by id

    :Args:
      team_id (string): the team's id
    """
    endpoint  = '/teams/{}'.format(team_id)
    return self._api_call('get', endpoint)

  def get_all_teams(self, **kwargs):
    """
    Get all teams for the authenticated user.

    :Args:
      account_id (string): The account id.
    """
    endpoint = '/teams'
    return self._api_call('get', endpoint, kwargs)

  def get_projects(self, team_id, **kwargs):
    """
    Get projects owned by the team.

    :Args:
      team_id (string): The team id.
    """
    endpoint = '/teams/{}/projects'.format(team_id)
    return self._api_call('get', endpoint, kwargs)
  
  def get_project(self, project_id):
    """
    Get an individual project

    :Args:
      project_id (string): the project's id
    """
    endpoint = '/projects/{}'.format(project_id)
    return self._api_call('get', endpoint)
  
  def get_collaborators(self, project_id, **kwargs):
    """
    Get collaborators for a project

    :Args:
      project_id (string): the project's id
    """
    endpoint = "/projects/{}/collaborators".format(project_id)
    return self._api_call('get', endpoint, kwargs)

  def get_pending_collaborators(self, project_id, **kwargs):
    """
    Get pending collaborators for a project

    :Args:
      project_id (string): the project's id
    """
    endpoint = "/projects/{}/pending_collaborators".format(project_id)
    return self._api_call('get', endpoint, kwargs)

  def create_project(self, team_id, **kwargs):
    """
    Create a project.

    :Args:
      team_id (string): The team id.
    :Kwargs:
      (optional) kwargs: additional request parameters.

      Example::

        client.create_project(
          team_id="123",
          name="My Awesome Project",
        )
    """
    endpoint = '/teams/{}/projects'.format(team_id)
    return self._api_call('post', endpoint, payload=kwargs)

  def get_project(self, project_id):
    """
    Get a project by id.

    :Args:
      project_id (string): The project id.
    """
    endpoint = '/projects/{}'.format(project_id)
    return self._api_call('get', endpoint)

  def get_asset(self, asset_id):
    """
    Get an asset by id.

    :Args:
      asset_id (string): The asset id.
    """
    endpoint = '/assets/{}'.format(asset_id)
    return self._api_call('get', endpoint)

  def get_asset_children(self, asset_id, **kwargs):
    """
    Get an asset's children.

    :Args:
      asset_id (string): The asset id.
    """
    endpoint = '/assets/{}/children'.format(asset_id)
    return self._api_call('get', endpoint, kwargs)

  def get_newest_assets(self, account_id, project_id, limit):
    """
    Get project's most recently added assets.

    :Args:
      account_id (string): The account id.
      project_id (string): The project id.
      limit (int): How many assets to get.
    """
    payload = {
      "account_id": account_id,
      "page": 1,
      "page_size": 50,
      "include": "children",
      "sort": "-inserted_at",
      "filter": {
        "project_id": {
          "op": "eq",
          "value": project_id
        }
      }
    }
    endpoint = '/search/library'
    return self._api_call('post', endpoint, payload=payload, limit=limit)

  def get_updated_assets(self, account_id, project_id, timestamp):
    """
    Get assets added or updated since timestamp.

    :Args:
      account_id (string): The account id.
      project_id (string): The project id.
      timestamp (string): ISO 8601 UTC format.
      (datetime.now(timezone.utc).isoformat())
    """
    payload = {
      "account_id": account_id,
      "page": 1,
      "page_size": 50,
      "include": "children",
      "sort": "-inserted_at",
      "filter": {
        "project_id": {
          "op": "eq",
          "value": project_id
        },
        "updated_at": {
          "op": "gte",
          "value": timestamp
        }
      }
    }
    endpoint = '/search/library'
    return self._api_call('post', endpoint, payload=payload)

  def create_asset(self, parent_asset_id, **kwargs):
    """
    Create an asset.

    :Args:
      parent_asset_id (string): The parent asset id.
    :Kwargs:
      (optional) kwargs: additional request parameters.

      Example::

        client.create_asset(
          parent_asset_id="123abc",
          name="ExampleFile.mp4",
          type="file",
          filetype="video/mp4",
          filesize=123456
        )
    """
    endpoint = '/assets/{}/children'.format(parent_asset_id)
    return self._api_call('post', endpoint, payload=kwargs)
  
  def update_asset(self, asset_id, **kwargs):
    """
    Updates an asset

    :Args:
      asset_id (string): the asset's id
    :Kwargs:
      the fields to update

      Example::
        client.update_asset("adeffee123342", name="updated_filename.mp4")
    """
    endpoint = '/assets/{}'.format(asset_id)
    return self._api_call('put', endpoint, kwargs)

  def delete_asset(self, asset_id):
    """
    Delete an asset

    :Args:
      asset_id (string): the asset's id
    """
    endpoint = '/assets/{}'.format(asset_id)
    return self._api_call('delete', endpoint)

  def upload(self, asset, file):
    """
    Upload an asset. The method will exit once the file is uploaded.

    :Args:
      asset (object): The asset object.
      file (file): The file to upload.

      Example::

        client.upload(asset, open('example.mp4')) // TODO fix this example (bad way of opening file)
    """
    uploader = FrameioUploader(asset, file)
    uploader.upload()
  
  def download(self, asset, download_folder, replace=True):
    """
    Download an asset. The method will exit once the file is downloaded.

    :Args:
      asset (object): The asset object.
      download_folder (path): The location to download the file to.

      Example::

        client.download(asset, "~./Downloads")
    """
    downloader = FrameioDownloader(asset, download_folder, replace)
    downloader.download()

  def get_comment(self, comment_id, **kwargs):
    """
    Get a comment.

    :Args:
      comment_id (string): The comment id.
    """
    endpoint = '/comments/{}'.format(comment_id)
    return self._api_call('get', endpoint, **kwargs)

  def get_comments(self, asset_id, **kwargs):
    """
    Get an asset's comments.

    :Args:
      asset_id (string): The asset id.
    """
    endpoint = '/assets/{}/comments'.format(asset_id)
    return self._api_call('get', endpoint, **kwargs)

  def create_comment(self, asset_id, **kwargs):
    """
    Create a comment.

    :Args:
      asset_id (string): The asset id.
    :Kwargs:
      (optional) kwargs: additional request parameters.

      Example::

        client.create_comment(
          asset_id="123abc",
          text="Hello world"
        )
    """
    endpoint = '/assets/{}/comments'.format(asset_id)
    return self._api_call('post', endpoint, payload=kwargs)

  def update_comment(self, comment_id, **kwargs):
    """
    Update a comment.

    :Args:
      comment_id (string): The comment id.
    :Kwargs:
      (optional) kwargs: additional request parameters.

      Example::

        client.create_comment(
          comment_id="123abc",
          text="Hello world"
        )
    """
    endpoint = '/comments/{}'.format(comment_id)
    return self._api_call('post', endpoint, payload=kwargs)

  def delete_comment(self, comment_id):
    """
    Delete a comment.

    :Args:
      comment_id (string): The comment id.
    """
    endpoint = '/comments/{}'.format(comment_id)
    return self._api_call('delete', endpoint)

  def get_review_links(self, project_id):
    """
    Get the review links of a project

    :Args:
      asset_id (string): The asset id.
    """
    endpoint = '/projects/{}/review_links'.format(project_id)
    return self._api_call('get', endpoint)

  def create_review_link(self, project_id, **kwargs):
    """
    Create a review link.

    :Args:
      project_id (string): The project id.
    :Kwargs:
      kwargs: additional request parameters.

      Example::

        client.create_review_link(
          project_id="123",
          name="My Review Link",
          password="abc123"
        )
    """
    endpoint = '/projects/{}/review_links'.format(project_id)
    return self._api_call('post', endpoint, payload=kwargs)

  def get_review_link(self, link_id, **kwargs):
    """
    Get a single review link

    :Args:
      link_id (string): The review link id.
    """
    endpoint = '/review_links/{}'.format(link_id)
    return self._api_call('get', endpoint, payload=kwargs)

  def update_review_link_assets(self, link_id, **kwargs):
    """
    Add or update assets for a review link.

    :Args:
      link_id (string): The review link id.
    :Kwargs:
      kwargs: additional request parameters.

      Example::

        client.update_review_link_assets(
          link_id="123",
          asset_ids=["abc","def"]
        )
    """
    endpoint = '/review_links/{}/assets'.format(link_id)
    return self._api_call('post', endpoint, payload=kwargs)

  def update_review_link(self, link_id, **kwargs):
    """
    Updates review link settings.

    :Args:
      link_id (string): The review link id.
    :Kwargs:
      kwargs: additional request parameters.

      Example::

        client.update_review_link(
          link_id,
          expires_at="2020-04-08T12:00:00+00:00",
          is_active=False,
          name="Review Link 123",
          password="my_fun_password",
        )
    """
    endpoint = '/review_links/{}'.format(link_id)
    return self._api_call('put', endpoint, payload=kwargs)

  def get_review_link_items(self, link_id):
    """
    Get items from a single review link.

    :Args:
      link_id (string): The review link id.

      Example::

        client.get_review_link_items(
          link_id="123"
        )
    """
    endpoint = '/review_links/{}/items'.format(link_id)
    return self._api_call('get', endpoint)
