import pathlib
import boto3
from dotenv import load_dotenv
import os
import asyncio
from pathlib import Path
import json
import importlib.resources as pkg_resources
from bidrunner2 import resources
from datetime import datetime
import toml

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import (
    Checkbox,
    DirectoryTree,
    Input,
    Button,
    Header,
    Markdown,
    Pretty,
    RichLog,
    Select,
    SelectionList,
    Label,
    Static,
    TabbedContent,
    TabPane,
)
from textual.containers import (
    Container,
    Horizontal,
    HorizontalScroll,
    Vertical,
    VerticalScroll,
)
from textual.validation import Length


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
        appdata_env = os.environ.get("LOCALAPPDATA")
        if appdata_env:
            local_appdata_path = pathlib.Path(appdata_env, "")
            config_path = local_appdata_path / "bidrunner2" / "config.toml"
            try:
                with open(config_path, "r") as f:
                    self.config = toml.load(f)
            except FileNotFoundError:
                raise Exception(
                    f"config file not found at {str(config_path)}, create one or pass in custom path with --config"
                )
        else:
            print("unable to find your homepath")

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

    def aws_set_credentials(self, access_key, secret_key, session_token):
        self.aws_creds = {}
        self.aws_creds["aws_access_key_id"] = access_key
        self.aws_creds["aws_secret_access_key"] = secret_key
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
            task_definition_revision = "13"
            task_definition = f"{task_definition_family}:{task_definition_revision}"
            self.logger.write(
                f"{log_with_timestamp()} running bid on cluster: {cluster_name}"
            )

            overwrite_command = ["Rscript", "track-message.R"]
            overwrite_command.extend(args)
            ecs_client = boto3.client("ecs", region_name="us-west-2", **self.aws_creds)
            resp = ecs_client.run_task(
                cluster=cluster_name,
                taskDefinition=task_definition,
                count=1,
                launchType="FARGATE",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": [
                            "subnet-00dbf1bd023906da2",
                            "subnet-0f8ae878792f9ba53",
                            "subnet-0be2ea73766e5a51a",
                            "subnet-03d9c808462943df1",
                        ],  # Replace with your subnet ID
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
        msg_attributes = {}
        msg_attributes = message.get("MessageAttributes")

        return {
            "id": msg_id,
            "receipt": msg_receipt,
            "body": msg_body,
            "name": list(msg_attributes.keys()),
            "attributes": msg_attributes,
        }

    async def check_sqs_Q(self, queue_url, bid_name):
        self.logger.write(
            "[bold yellow]Fetching and processing SQS messages with Polling time of 20 seconds...[/bold yellow]"
        )
        sqs_client = boto3.client("sqs", region_name="us-west-2", **self.aws_creds)

        try:
            response = await asyncio.to_thread(
                sqs_client.receive_message,
                QueueUrl=queue_url,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )

            messages = response.get("Messages", [])
            message_processed = [self.sqs_process_message(m) for m in messages]
            message_filtered_to_task = [
                m for m in message_processed if m.get("name") == [bid_name]
            ]
            if message_processed:
                sorted_messages = message_filtered_to_task

                for message in sorted_messages:
                    try:
                        content = str(
                            message.get("body")
                        )  # Convert the entire body to a string
                        self.sqs_status.append(
                            f"Task name: {message.get('name')} - {content}"
                        )

                        # Delete the message from the queue
                        try:
                            await asyncio.to_thread(
                                sqs_client.delete_message,
                                QueueUrl=queue_url,
                                ReceiptHandle=message.get("receipt"),
                            )
                        except Exception as delete_error:
                            self.logger.write(
                                f"[bold red]Error deleting message: {delete_error}[/bold red]"
                            )
                    except json.JSONDecodeError as e:
                        self.logger.write(
                            f"[bold red]Error decoding JSON: {e}. Raw message: {message.get('body')}[/bold red]"
                        )
            else:
                self.logger.write("[bold blue]No new messages found.[/bold blue]")

        except Exception as e:
            self.logger.write(f"[bold red]Error processing messages: {e}[/bold red]")

        finally:
            self.logger.write("[bold yellow]Message processing complete.[/bold yellow]")
            self.logger.write("[bold blue]Current SQS status:[/bold blue]")
            for idx, message in enumerate(self.sqs_status, 1):
                self.logger.write(f"{idx}. {message}")

            self.sqs_status = []

    async def check_bid_status(self, q_url, bid_name, follow=False):
        if follow:
            pass
        else:
            self.check_task_status()
            await self.check_sqs_Q(q_url, bid_name)

            if len(self.task_status) > 0:
                self.logger.write(
                    f"[bold magenta]Task - status:[/bold magenta] {self.task_status.pop()}"
                )
            else:
                self.logger.write("[bold magenta]Task - no new messages[/bold magenta]")

    def s3_get_all_buckets(self):
        s3_cl = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
        all_buckets = s3_cl.list_buckets()

        return [(bucket["Name"], bucket["Name"]) for bucket in all_buckets["Buckets"]]

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
        try:
            self.runner.aws_set_credentials(
                os.getenv("AWS_ACCESS_KEY_ID"),
                os.getenv("AWS_SECRET_ACCESS_KEY"),
                os.getenv("AWS_SESSION_TOKEN"),
            )
            self.account_bucket_list = self.runner.s3_get_all_buckets()
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

        dir_tree = DirectoryTree(os.environ.get("homepath"), id="dir-tree")
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
                        # Input(
                        #     placeholder="Input data bucket",
                        #     id="bid-input-bucket",
                        #     classes="input-focus input-element",
                        # ),
                        Select(
                            self.account_bucket_list,
                            prompt="Select Input Bucket",
                            id="bid-input-bucket",
                            classes="input-focus input-element",
                        ),
                        Input(
                            placeholder="Auction Id",
                            id="bid-auction-id",
                            classes="input-focus input-element",
                        ),
                        Input(
                            placeholder="Auction shapefile",
                            id="bid-auction-shapefile",
                            classes="input-focus input-element",
                        ),
                        Input(
                            placeholder="enter bid split id",
                            id="bid-split-id",
                            classes="input-focus input-element",
                        ),
                        Input(
                            placeholder="enter bid id",
                            id="bid-id",
                            classes="input-focus input-element",
                        ),
                        SelectionList[int](
                            ("January", 0, True),
                            ("February", 1),
                            ("March", 2),
                            ("April", 3),
                            ("May", 4),
                            ("June", 5),
                            id="bid-months",
                            classes="input-focus input-element",
                        ),
                        Input(
                            placeholder="Waterfiles",
                            id="bid-waterfiles",
                            classes="input-focus input-element",
                        ),
                        Select(
                            self.account_bucket_list,
                            prompt="Select Outpu Bucket",
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
                        Checkbox(
                            "Follow bid logs after submission (will block app)",
                            id="follow-logs",
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
                                self.account_bucket_list,
                                prompt="Select Destination Bucket",
                            ),
                            Button("Upload", id="data-upload"),
                            id="data-right",
                        ),
                    ),
                    id="data-ui",
                )
            with TabPane("Existing Bids"):
                yield Markdown("## Check Existing Runs")
            with TabPane("Manual"):
                manual_path = get_resource_path("manual.md")
                if manual_path:
                    with open(manual_path, "r") as f:
                        yield Markdown(f.read(), id="manual-ui")

    def validate_inputs_and_notify(self) -> bool:
        all_pass = True
        input_ids = [
            "#bid-name",
            # "#bid-input-bucket",
            "#bid-auction-id",
            "#bid-auction-shapefile",
            "#bid-split-id",
            "#bid-id",
            # "#bid-months",
            "#bid-waterfiles",
            # "#bid-output-bucket",
        ]
        show_notification = False
        for id in input_ids:
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
            # "#bid-input-bucket",
            "#bid-auction-id",
            "#bid-auction-shapefile",
            "#bid-split-id",
            "#bid-id",
            # "#bid-months",
            "#bid-waterfiles",
            # "#bid-output-bucket",
        ]
        for id in input_ids:
            elem = self.query_one(id, Input)
            if elem.value:
                elem.remove_class("error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one(RichLog)
        self.runner.set_logger(log)
        if event.button.id == "submit-aws-connection-check":
            creds_ok = self.runner.aws_check_credentials()
            notify_severity = "information" if creds_ok else "error"
            self.notify(
                f"{'Your credentials look good!' if creds_ok else 'Ooop! Your credentials are not valid, check logs for details'}",
                title="AWS Credential Check",
                severity=notify_severity,
            )
            # log.write(f"Connected to aws? {'Yes' if creds_ok else 'No'}")
        if event.button.id == "submit_run":
            bid_name = self.query_one("#bid-name", Input).value
            bid_input_bucket = self.query_one("#bid-input-bucket", Select).value
            bid_auction_id = self.query_one("#bid-auction-id", Input).value
            bid_auction_shapefile = self.query_one(
                "#bid-auction-shapefile", Input
            ).value
            bid_split_id = self.query_one("#bid-split-id", Input).value
            bid_id = self.query_one("#bid-id", Input).value
            bid_months = self.query_one("#bid-months", SelectionList).selected
            bid_waterfiles = self.query_one("#bid-waterfiles", Input).value
            bid_output_bucket = self.query_one("#bid-output-bucket", Select).value

            follow_logs = self.query_one("#follow-logs", Checkbox).value

            months = [
                "jan",
                "feb",
                "mar",
                "apr",
                "may",
                "jun",
                "jul",
                "aug",
                "sep",
                "oct",
                "nov",
                "dec",
            ]
            selected_months = [months[i] for i in bid_months]

            all_inputs = [
                bid_name,
                bid_input_bucket,
                bid_auction_id,
                bid_auction_shapefile,
                bid_split_id,
                bid_id,
                ",".join(selected_months),
                bid_waterfiles,
                bid_output_bucket,
            ]

            queue_url = (
                "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"
            )

            if self.validate_inputs_and_notify():
                self.runner.run(all_inputs)

        if event.button.id == "check-task-status":
            bid_name = self.query_one("#bid-name", Input).value
            queue_url = (
                "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"
            )
            await self.runner.check_bid_status(queue_url, bid_name)
        if event.button.id == "clear-logs":
            log.clear()
        if event.button.id == "clear-form":
            input_ids = [
                "#bid-name",
                # "#bid-input-bucket",
                "#bid-auction-id",
                "#bid-auction-shapefile",
                "#bid-split-id",
                "#bid-id",
                # "#bid-months",
                "#bid-waterfiles",
                # "#bid-output-bucket",
            ]
            for id in input_ids:
                elem = self.query_one(id, Input)
                elem.clear()
                elem.remove_class("error")
        if event.button.id == "data-upload":
            dir_tree_elem = self.query_one("#dir-tree", DirectoryTree)
            selected_folder_ui = self.query_one(Pretty)
            selected_folder_ui.update(
                f"Selected folder for Upload: {dir_tree_elem.cursor_node.data.path}"
            )
            self.runner.s3_sync_to_bucket(
                dir_tree_elem.cursor_node.data.path, "s3://my-bucket"
            )
            log.write(f"{dir_tree_elem.cursor_node.data.path}")

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
