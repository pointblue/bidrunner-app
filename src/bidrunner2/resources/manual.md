# Bidrunner2 Manual

##### *to view a version of this manual on a word document (`.docx`), please download from [here](#)*

## App Configuration

In order to run the app (and view this Manual here) you must have created a config file in your local app directory. There are many
settings you can change not all listed in the auto-generated log file, these are listed here.


## New Bid

The new bid tab provides a form for adding runtime parameters changes to a bid. All inputs are required. 

Descriptions for inputs:

- Bid Name: this is a unique name used to identify the run on AWS.
- Input data bucket: provide a bucket name that hosts the data used for the input. This field is a dropdown, you can select from s3 buckets available to your role within the organization
- Auction ID: the auction ID used to identify folder within the input data.
- Auction Shapefile: the shapefile used during rasterization process.
- Auction Split ID: the column name used to split id's for auction runs

### Submit at Bid

To submit a bid simply fill out form and press submit, this will use your credentials and send AWS a request to spin up a vm capable of running the bid. As part of this process the
services used to carry out this process will start to publish log messages that `bidrunner2` can display for you. Press the `Check Task Status` to view an update message log from 
both the VM and the model output.

The output format for these logs seperate the `task` and `bid` logs as follows:

```bash
 fdjska
 f
 dsa
 f
 dsa



```

 
## Existing Bid


## Manual

This Manual. To download a word version of this manual click [here](#)

This is test to 
