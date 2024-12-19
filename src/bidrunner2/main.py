import pathlib
import boto3
from dotenv import load_dotenv
import os
import json
import importlib.resources as pkg_resources
from bidrunner2 import resources
from datetime import datetime
import toml
import platform

from textual import message, on
from textual.app import App, ComposeResult
from textual.widgets import (
    DirectoryTree,
    Input,
    Button,
    Header,
    Markdown,
    Pretty,
    RichLog,
    Select,
    TabbedContent,
    TabPane,
)
from textual.containers import (
    Container,
    Horizontal,
    HorizontalScroll,
    VerticalScroll,
)


# Helper Functions --------------------------------------------


def get_resource_path(filename):
    try:
        with pkg_resources.path(resources, filename) as path:
            return str(path.resolve())
    except Exception as e:
        print(f"Error getting path for resource {filename}: {e}")
        return None


def get_root_path(filename):
    try:
        with pkg_resources.path(".", filename) as path:
            return str(path.resolve())
    except Exception as e:
        print(f"Error getting path for resource {filename}: {e}")
        return None


def get_resource_content(filename):
    try:
        return pkg_resources.read_text(resources, filename)
    except Exception as e:
        print(f"Error reading resource {filename}: {e}")
        return None


def log_with_timestamp():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[bold green][{ts}][/bold green]"


# Bidrunner AWS ----------------------------------------


class BidRunner:
    def __init__(self):
        self.aws_credentials_set = False
        self.aws_creds = {}
        self.runner_details = {}
        self.sqs_status = []
        self.task_status = []
        self.config = None

    def load_config(self):
        if platform.system() == "Windows":
            appdata_env = os.environ.get("LOCALAPPDATA")
        elif platform.system() == "Linux":
            appdata_env = f'{os.environ.get("HOME")}/.config'
        local_appdata_path = pathlib.Path(appdata_env, "")
        config_path = local_appdata_path / "bidrunner2" / "config.toml"
        try:
            with open(config_path, "r") as f:
                self.config = toml.load(f)
        except FileNotFoundError as e:
            raise Exception(str(e))

    def set_logger(self, log: RichLog):
        self.logger = log

    def _parse_base_ecs_definition(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "resources", "ecs-def.json")
        with open(json_path) as f:
            ecs_def = json.load(f)
        return ecs_def

    def create_task_definition(self, args):
        ecs_def = self._parse_base_ecs_definition()
        ecs_def.get("containerDefinitions")[0]["environment"] = [
            {"name": k, "value": v} for k, v in self.aws_creds.items()
        ]
        ecs_def.get("containerDefinitions")[0]["commands"] = args
        return ecs_def

    def overwrite_task_definitions(self, cluster_name, task_name, args):
        return {
            "cluster": cluster_name,
            "taskDefinition": task_name,
            "launchType": "FARGATE",  # or 'FARGATE' if using Fargate
            "overrides": {
                "containerOverrides": [
                    {
                        "name": "water-tracker",
                        "command": args,
                        "environment": [
                            {"name": k, "value": v} for k, v in self.aws_creds.items()
                        ],
                    },
                ],
            },
            "count": 1,
        }

    def aws_set_credentials(self, access_key, secret_key, session_token=None):
        self.aws_creds = {}
        self.aws_creds["aws_access_key_id"] = access_key
        self.aws_creds["aws_secret_access_key"] = secret_key
        if session_token:
            self.aws_creds["aws_session_token"] = session_token

    def aws_check_credentials(self):
        self.logger.write("[bold green]AWS Credentials Check: =================")
        try:
            s3 = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
            _ = s3.list_buckets()
            self.logger.write("Succesully performed AWS credential check")
            return True
        except Exception as e:
            self.logger.write(
                "Unable to connect to aws. The following error was received:"
            )
            self.logger.write(f"[bold magenta]{e}")
            self.logger.write(
                "Your aws credentials should be set in an [bold green]`.env`[/bold green] file in the same directory where this app is being run. Consult the manual for details on the format of this file."
            )
            return False
        finally:
            self.logger.write("[bold green]=================")

    def run(self, args):
        try:
            cluster_name = "WaterTrackerDevCluster"
            task_definition_family = "water-tracker-model-runs"
            task_definition_revision = "23"
            task_definition = f"{task_definition_family}:{task_definition_revision}"
            self.logger.write(
                f"{log_with_timestamp()} running bid on cluster: {cluster_name}"
            )

            # overwrite container commands with those from the app
            overwrite_command = ["bash", "execute.sh"]
            overwrite_command.extend(args)

            ecs_client = boto3.client("ecs", region_name="us-west-2", **self.aws_creds)
            resp = ecs_client.run_task(
                cluster=cluster_name,
                taskDefinition=task_definition,
                count=1,
                launchType="FARGATE",
                # TODO: needs to changed when transfering ownership
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": [
                            "subnet-00dbf1bd023906da2",
                            "subnet-0f8ae878792f9ba53",
                            "subnet-0be2ea73766e5a51a",
                            "subnet-03d9c808462943df1",
                        ],
                        "assignPublicIp": "ENABLED",
                    }
                },
                overrides={
                    "containerOverrides": [
                        {
                            "name": "water-tracker",
                            "command": overwrite_command,
                            "environment": [
                                {"name": k.upper(), "value": v}
                                for k, v in self.aws_creds.items()
                            ],
                        }
                    ]
                },
            )

            task_arn = resp["tasks"][0]["taskArn"]
            self.logger.write(
                f"{log_with_timestamp()} created new task at: [bold green]{task_arn}[/bold green]"
            )
            self.logger.write(
                f"{log_with_timestamp()} you can continue to check status by clicking [bold green]`Check Task Status`[/bold green]"
            )

            self.runner_details["cluster"] = cluster_name
            self.runner_details["tasks"] = [task_arn]

        except Exception as e:
            self.logger.write(
                f"{log_with_timestamp()} An error occured trying to run the task"
            )
            self.logger.write(f"{e}")

    def get_all_running_tasks(self):
        """
        Get a list of all the running tasks that are related to water tracker
        """
        ecs_cl = boto3.client("ecs", **self.aws_creds, region_name="us-west-2")
        resp = ecs_cl.list_tasks(
            cluster="WaterTrackerDevCluster", desiredStatus="RUNNING"
        )
        task_list = resp.get("taskArns")
        return task_list

    def check_task_status(self):
        if len(self.runner_details) == 0:
            self.logger.write(
                f"runner details is empty, did you run the a bid first? Value of runner_details: {self.runner_details}"
            )
        if not self.runner_details.get("tasks") or not self.runner_details.get(
            "cluster"
        ):
            self.logger.write(
                f"invalid values for tasks and cluster, these are tasks={self.runner_details.get('tasks')} and cluster={self.runner_details.get('cluster')}"
            )
        else:
            cl = boto3.client("ecs", region_name="us-west-2", **self.aws_creds)
            res = cl.describe_tasks(**self.runner_details)
            task = res["tasks"][0]
            last_status = task["lastStatus"]
            self.task_status.append(last_status)

    def sqs_process_message(self, message):
        msg_id = message.get("MessageId")
        msg_receipt = message.get("ReceiptHandle")
        msg_body = message.get("Body")
        msg_sent_timestamp = message.get("Attributes").get("SentTimestamp")
        msg_bid_name = (
            message.get("MessageAttributes").get("bid_name").get("StringValue")
        )

        return {
            "id": msg_id,
            "receipt": msg_receipt,
            "body": msg_body,
            "timestamp": datetime.fromtimestamp(int(msg_sent_timestamp) / 1000),
            "bid_name": msg_bid_name,
        }

    def get_latest_sqs_message(self, queue_url, bid_name):
        sqs_client = boto3.client("sqs", region_name="us-west-2", **self.aws_creds)
        try:
            resp = sqs_client.receive_message(
                QueueUrl=queue_url,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )

            messages = resp.get("Messages", [])
            messages_processed = [self.sqs_process_message(m) for m in messages]
            messages_filtered_to_task = [
                m for m in messages_processed if m.get("bid_name") == bid_name
            ]

            if messages_filtered_to_task:
                sorted_messages = sorted(
                    messages_filtered_to_task, key=lambda x: x["timestamp"]
                )
                for message in sorted_messages:
                    content = str(message.get("body"))
                    self.sqs_status.append(
                        f"[bold magenta]{log_with_timestamp()}[/bold magenta][bold cyan]{bid_name}[/bold cyan] - {content}"
                    )

                    sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message.get("receipt"),
                    )
        except Exception as e:
            self.logger.write(f"[bold red] Error procesing messages {e}[/bold red]")

    def check_bid_status(self, q_url, bid_name):
        self.logger.write(
            "[bold orange]Retrieving latest messages from Queue...[/bold orange]"
        )
        self.check_task_status()
        self.get_latest_sqs_message(q_url, bid_name)

        if len(self.task_status) > 0:
            self.logger.write(
                f"[bold magenta]Task - status:[/bold magenta] {self.task_status.pop()}"
            )
        else:
            self.logger.write("[bold magenta]Task - no new messages[/bold magenta]")

    def s3_get_all_buckets(self, s3_root):
        s3_cl = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
        paginator = s3_cl.get_paginator("list_objects_v2")
        folders = []

        for page in paginator.paginate(Bucket=s3_root, Delimiter="/"):
            for prefix in page.get("CommonPrefixes", []):
                folders.append(prefix["Prefix"])

        return [(f, f) for f in folders]

    def efs_get_all_folders(self):
        all_folders = os.listdir("/mnt/efs")
        return [(f, f) for f in all_folders]

    # TODO: maybe remove this? I think we should just instruct users to use the aws cli
    def s3_sync_to_bucket(self, source, destination):
        s3_cl = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
        for root, dirs, files in os.walk(source):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, source)
                s3_path = os.path.join(destination, relative_path)

                self.logger.write(f"Uploading {local_path} to {destination}/{s3_path}")

    def __repr__(self):
        return "<BidRunner Input>"


# App ---------------------------------------------------


class BidRunnerApp(App):
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # CSS_PATH = os.path.join(current_dir, "resources", "styles.tcss")

    CSS_PATH = get_resource_path("styles.tcss")

    def on_load(self) -> None:
        load_dotenv()
        self.runner = BidRunner()
        self.runner.load_config()
        self.selected_folder_to_upload = None
        s3_input_root = self.runner.config["app"]["s3_input_root"]
        s3_output_root = self.runner.config["app"]["s3_output_root"]
        try:
            self.runner.aws_set_credentials(
                self.runner.config["aws"]["aws_access_key_id"]
                or os.getenv("AWS_ACCESS_KEY_ID"),
                self.runner.config["aws"]["aws_secret_access_key"]
                or os.getenv("AWS_SECRET_ACCESS_KEY"),
                None,
            )
            self.account_input_bucket_list = self.runner.s3_get_all_buckets(
                s3_input_root
            )
            self.account_output_bucket_list = self.runner.s3_get_all_buckets(
                s3_output_root
            )
        except Exception as e:
            raise Exception(
                f"Unable to connect to aws using provided credentials, received the following error: {e}"
            )

    def on_mount(self) -> None:
        self.title = "Bidrunner2"
        self.notify("Welcome to bidrunner2!")

    def compose(self) -> ComposeResult:
        rl = RichLog(
            auto_scroll=True, highlight=True, markup=True, id="bid-run-logs", wrap=True
        )
        rl.border_title = "Run Logs"

        if platform.system() == "Windows":
            home_path_for_tree = os.environ.get("homepath")
        elif platform.system() == "Linux":
            home_path_for_tree = "~"

        dir_tree = DirectoryTree(home_path_for_tree, id="dir-tree")
        dir_tree.border_title = "Local Source"

        yield Header()
        with TabbedContent():
            with TabPane("New Bid"):
                yield HorizontalScroll(
                    VerticalScroll(
                        Input(
                            placeholder="Bid Name",
                            id="bid-name",
                            classes="input-focus input-element",
                        ),
                        Select(
                            self.account_input_bucket_list,
                            prompt="Select Input Bucket/Auction ID",
                            id="bid-input-bucket",
                            classes="input-focus input-element",
                        ),
                        # Input(
                        #     placeholder="Auction Id",
                        #     id="bid-auction-id",
                        #     classes="input-focus input-element",
                        # ),
                        Input(
                            placeholder="Auction shapefile",
                            id="bid-auction-shapefile",
                            classes="input-focus input-element",
                        ),
                        Select(
                            self.account_output_bucket_list,
                            prompt="Select Output Bucket",
                            id="bid-output-bucket",
                            classes="input-focus input-element",
                        ),
                        Horizontal(
                            Button(
                                "Submit",
                                id="submit_run",
                                variant="default",
                            ),
                            Button(
                                "Check Task Status",
                                id="check-task-status",
                                variant="default",
                            ),
                            Button("Clear Form", id="clear-form", variant="default"),
                            id="buttons-row",
                        ),
                        id="main-ui",
                    ),
                    Container(
                        rl,
                        Button("Clear Logs", id="clear-logs", variant="error"),
                        id="log_ui",
                    ),
                )
            with TabPane("Data"):
                yield Container(
                    Horizontal(
                        Container(
                            dir_tree,
                            id="data-left",
                        ),
                        Container(
                            Pretty(
                                "Select folder for upload"
                                if self.selected_folder_to_upload is None
                                else self.selected_folder_to_upload,
                                id="selected-folder-to-upload",
                            ),
                            Select(
                                self.account_input_bucket_list,
                                prompt="Select Destination Bucket",
                            ),
                            Button("Upload", id="data-upload"),
                            RichLog(id="aws-cli-command", markup=True, max_lines=3),
                            id="data-right",
                        ),
                    ),
                    id="data-ui",
                )
            with TabPane("Manual"):
                manual_path = get_resource_path("manual.md")
                if manual_path:
                    with open(manual_path, "r") as f:
                        yield Markdown(f.read(), id="manual-ui")

    def validate_inputs_and_notify(self) -> bool:
        all_pass = True
        input_ids = [
            "#bid-name",
            "#bid-input-bucket",
            # "#bid-auction-id",
            "#bid-auction-shapefile",
            "#bid-output-bucket",
        ]
        show_notification = False
        for id in input_ids:
            if "bucket" in id:
                widget_element = self.query_one(id, Select)
            else:
                widget_element = self.query_one(id, Input)
            if not widget_element.value:
                show_notification = True
                all_pass = False
                widget_element.add_class("error")
            else:
                widget_element.remove_class("error")
        if show_notification:
            self.notify(
                "invalid form, please submit all required fields", severity="error"
            )

        return all_pass

    @on(Input.Changed)
    def remove_error_class(self):
        input_ids = [
            "#bid-name",
            "#bid-input-bucket",
            # "#bid-auction-id",
            "#bid-auction-shapefile",
            "#bid-output-bucket",
        ]
        for id in input_ids:
            if "bucket" in id:
                elem = self.query_one(id, Select)
            else:
                elem = self.query_one(id, Input)
            if elem.value:
                elem.remove_class("error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#bid-run-logs", RichLog)
        self.runner.set_logger(log)
        queue_url = self.runner.config["aws"]["queue_url"]

        if event.button.id == "submit_run":
            bid_name = self.query_one("#bid-name", Input).value
            bid_input_bucket = self.query_one("#bid-input-bucket", Select).value
            # bid_auction_id = self.query_one("#bid-auction-id", Input).value
            bid_auction_shapefile = self.query_one(
                "#bid-auction-shapefile", Input
            ).value
            bid_output_bucket = self.query_one("#bid-output-bucket", Select).value

            all_inputs = [
                bid_name,
                bid_input_bucket,  # this is auction id
                bid_auction_shapefile,
                bid_output_bucket,
            ]

            if self.validate_inputs_and_notify():
                self.runner.run(all_inputs)

        if event.button.id == "check-task-status":
            bid_name = self.query_one("#bid-name", Input).value
            log.write("[bold orange]Retrieving message from SQS Queue[/bold orange]")
            self.runner.check_bid_status(queue_url, bid_name)
            for msg in self.runner.sqs_status:
                log.write(f"[bold green]{msg}[/bold green]")
        if event.button.id == "clear-logs":
            log.clear()
        if event.button.id == "clear-form":
            input_ids = [
                "#bid-name",
                "#bid-input-bucket",
                # "#bid-auction-id",
                "#bid-auction-shapefile",
                "#bid-output-bucket",
            ]
            for id in input_ids:
                elem = self.query_one(id, Input)
                elem.clear()
                elem.remove_class("error")
        if event.button.id == "data-upload":
            dir_tree_elem = self.query_one("#dir-tree", DirectoryTree)
            aws_cli_ui = self.query_one("#aws-cli-command", RichLog)
            selected_folder_ui = self.query_one(Pretty)
            selected_folder_ui.update(
                f"Selected folder for Upload: {dir_tree_elem.cursor_node.data.path}"
            )

            selected_dir = dir_tree_elem.cursor_node.data.path
            selected_dir = str(selected_dir)
            selected_dir = selected_dir.replace("\\", "/")

            aws_cli_ui.write(
                f"Run the following on a terminal to copy data to S3, wait for it finish and return to new bid to select it:\n\n[bold #AAAAAA on #162138]aws s3 sync {selected_dir} s3://destination[/bold #AAAAAA on #162138]"
            )

    @on(DirectoryTree.DirectorySelected)
    def update_pretty_output(self):
        dir_tree_elem = self.query_one("#dir-tree", DirectoryTree)
        selected_folder_value = dir_tree_elem.cursor_node.data.path
        selected_folder_ui = self.query_one(Pretty)
        selected_folder_to_show = (
            f"Selected folder for upload: {selected_folder_value}"
            if selected_folder_value
            else "Select a folder to upload"
        )
        selected_folder_ui.update(selected_folder_to_show)


def main():
    app = BidRunnerApp()
    app.run()


if __name__ == "__main__":
    main()
