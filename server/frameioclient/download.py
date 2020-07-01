import requests
import os

class FrameioDownloader(object):
  def __init__(self, asset, download_folder, replace):
    self.asset = asset
    self.download_folder = download_folder
    self.replace = replace

  def download(self):
    original_filename = self.asset['name']
    final_destination = os.path.join(self.download_folder, original_filename)
    
    url = self.asset['original']
    r = requests.get(url)

    if os.path.isfile(final_destination) and not self.replace:
        raise FileExistsError

    open(final_destination, 'wb').write(r.content)
    