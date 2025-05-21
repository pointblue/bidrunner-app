# bidrunner2 

An interface for deploying auction evaluations.

## Install

To install the **bidrunner2** interface you will need at least python 3.8. 


```bash
pipx install git+https://github.com/pointblue/bidrunner-app.git --force 
```

This will install an executable that can be spawned by running `bidunner2.exe` from the commmand line.

A config file is required to run. On Windows this file is expected to be in `%LOCALAPPDATA%/bidrunner2/config.toml` and on unix systems in `~/.config/bidrunner2/config.toml`. Replace values with your
own:


```toml
[app]
# the bucket where all the data inputs are stored, this should be full of "auction_id" folders
s3_input_root = "bid-runner-input-2024"
# the bucket where outputs are to be saved, bidrunner will create new folders within this bucket to store run ouputs
s3_output_root = "bid-runner-output-2024"

[aws]
aws_access_key_id = ""
aws_secret_access_key = ""
aws_session_token = ""
queue_url = ""
```


![Drawing 2024-06-14 15 20 26 excalidraw](https://github.com/FlowWest/bidrunner2/assets/10622214/018cf571-9655-4b50-8266-a1d6459b58a0)
