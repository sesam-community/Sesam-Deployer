[![Build Status](https://travis-ci.org/sesam-community/oracle-transform.svg?branch=master)](https://travis-ci.org/sesam-community/oracle-transform)

# Sesam Auto Deployer
* ## What do I do?
I upload a sesam node config from one or more github repo's to a sesam node instance.<br>
The git repo needs whitelist and variables files. to distinguish between production and test environment.<br>
Whitelist-suffix.txt files located here:<br>
`node/deployment/whitelist-suffix.txt` <br>
Variables file variables-suffix.json. located here: <br> 
`node/variables/variables-suffix.json` <br>

Script which should be triggered after a merge into a branch on github by azure pipelines. <br>

* ##Environment variables
```
VAULT_GIT_TOKEN=git_token_used_to_access_vault
VAULT_MOUNTING_POINT=outer_folder_name/kv2
VAULT_URL=https://vault.organization.io
GIT_USERNAME=xyz
GIT_PASSWORD=xyz
GIT_REPOSITORIES=[
  {
    "URL": "github.com/organization/repo_name.git",
    "BRANCH": "master"
  },
  {
    "URL": "github.com/organization/more_repo_name.git",
    "BRANCH": "master"
  }
]
NODE_URL=xyz.sesam.cloud
NODE_ENV=test
NODE_JWT=ey...
```

It can also be used as a docker container though it is not set up to automatically check for changes to the git repository.

* ## How do i run it?
    * ### In the terminal:
        1. Create virtualenv.
            ```
            virtualenv --python=python3 .venv
            source .venv/bin/activate
            ```
        2.  Install requirements.
            ```
            pip install -r requirements.txt
            ```
        
        3. Run. Make sure all the required environment variables are available in the local context.
            ```
            cd service
            python deployer.py
            ```
        4. Stop virtualenv
            ```
            deactivate
            ```
     * ### In pycharm
        1. Open project
        2. Right click on 'deployer.py' and click run.
        3. After first run fails:
            * Click on Run -> Edit Configurations
            * Add environment variables.
        4. Run it again.
        

* ## I want to improve this! What can I do?
    * Add support for keyvault 1 (kv1)
    * Add support for different authorization options for vault.
    * Add support for different secret storage services.
    * Add support for customized node configurations (E.g no whitelist files, no variables file.)
    * Add support for checking for git repo changes so it could be used as a microservice on an independent node (you probably should not deploy to the node your running the microservice on).
             