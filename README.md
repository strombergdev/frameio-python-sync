# Frame.io python sync 

Keep a local server syncronized with Frame.io.


### Development Setup

##### Dev token login (only one login method required):
1. Create a dev token at [developer.frame.io](https://developer.frame.io)
    - Scopes required: project.read asset.create offline asset.read team.read account.read asset.delete

##### OAuth login:
1. Create a PKCE OAuth app at [developer.frame.io](https://developer.frame.io)
    - Scopes required: project.read asset.create offline asset.read team.read account.read asset.delete
    - Running on localhost:
        - Set Redirect URIs to http://127.0.0.1:8080
    - Running on server:  
        - Set Redirect URIs to [http://SERVER_IP:5111](http://SERVER_IP:5111)
2. Enter CLIENT_ID and REDIRECT_URL into config.py


##### Setup/start server:
1. Run `make install`
2. Run `make api`
3. Running on Localhost:
    - In another shell environment, run `make web`
    - Go to [http://127.0.0.1:8080](http://127.0.0.1:8080)
   
   Running on server:
    - Build frontend with `make buildweb`
    - Go to [http://SERVER_IP:5111](http://SERVER_IP:5111)    
    
5. Login in the top right
7. Choose what folders you want to sync!


### Sync flow (every 60 seconds):    

    - Frame.io is asked for all projects in all teams, new ones are added to database.
    
    - Frame.io is asked for the number of files and folders in each project.
    - The file size of the local sync folder is calculated.
    
    - If the size(s) have changed, the project is flagged as updated.
    - Updated projects are scanned for all files and folders and new assets are added to database.
    - New files are uploaded/downloaded.

### Policy
     
Uploads


    - Local files are considered ready for upload if their size hasn't changed in the last 5 secs.
    - If the local xxhash does not match Frame.io's hash, the asset is deleted on Frame.io and re-uploaded.
    - Assets are deleted and re-uploaded 3 times max.

Downloads


    - Frame.io assets are considered ready for download when upload_completed_at is not None.
    - Downloads are not verified at the moment.
    

Deleting files


    - Deleting a file on Frame.io will not delete it locally.
    - Deleting a file locally will not delete it on Frame.io.
    - Deleting a file in one location will not re-download/re-upload it again.
    
    - If you add a new file with the same name as a deleted one, it will not be synced. 
    
    


Duplicates


    - Multiple assets with the same path and name/team: only the first one to be discovered will be synced.
    - If you replace a file it will not be re-uploaded since the name is still the same.
    
Renames


    - Are ONLY supported for a project name.
    - If you rename a local file or folder, it will be uploaded as a new asset to Frame.io.
    - If you rename a Frame.io asset, the corresponding local asset will not be changed.
    