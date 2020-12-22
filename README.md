### Synchronize a server with Frame.io.


![Screenshot 2020-07-17 at 13 26 11](https://user-images.githubusercontent.com/63540107/87785797-176e0a00-c839-11ea-9987-f368c7494725.png)


### Setup

##### Requirements: Python 3.5-3.7 and npm.

##### Dev token login (only one login method required):
1. Create a dev token at [developer.frame.io](https://developer.frame.io)
    - Required scopes: asset.read, asset.create, asset.delete, project.read, team.read, account.read


##### OAuth login:
1. Create a PKCE OAuth app at [developer.frame.io](https://developer.frame.io)
    - Required scopes: offline, asset.read, asset.create, asset.delete, project.read, team.read, account.read
    - Running on localhost:
        - Set Redirect URIs to http://127.0.0.1:8080
    - Running on server:  
        - Set Redirect URIs to [http://SERVER_IP:5111](http://SERVER_IP:5111)
2. Enter CLIENT_ID and REDIRECT_URL into config.py


##### Setup/start server:
1. Run `make install`
2. To run frontend dynamically with VUE hot-reload for development:
    - Run `make api`
    - In another shell environment, run `make web`
    - Go to [http://127.0.0.1:8080](http://127.0.0.1:8080)
   
   To build frontend, when you just want to run without changing stuff:
    - Run `make buildweb`
    - Run `make api`    
    - Go to [http://127.0.0.1:5111](http://127.0.0.1:5111) or [http://SERVER_IP:5111](http://SERVER_IP:5111)
   
4. Login in the top right
5. Choose what folders you want to sync!


### Sync Policy
     
Uploads


    - Local files are considered ready for upload if they haven't been updated in the last 60 secs.
    - Uploads are verified with XXHash and retried up to 3 times.

Downloads


    - Frame.io assets are considered ready for download when upload_completed_at is not None.
    - Downloads are verified with XXHash and retried up to 3 times.
    

Deleting files


    - Deletions are not synced, i.e deleting a file on Frame.io will not delete it locally and vice versa.
    - If you add a new file with the same name as a deleted one, it will not be synced. 
    

Duplicates


    - Multiple assets with the same path/name: only the first one to be discovered will be synced.
    - If you replace a file it will not be re-uploaded since the name is still the same.
    
Renames


    - ONLY supported for project name.
    - If you rename a local file or folder, it will be uploaded as a new asset to Frame.io.
    - If you rename a Frame.io asset, the corresponding local asset will not be changed.
    

Using a fork of the [official python client](https://github.com/Frameio/python-frameio-client).
Thanks to [Jeff](https://github.com/jhodges10) at Frame.io for great input and support! 
