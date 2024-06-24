import boto3
from dotenv import load_dotenv
import os
import asyncio
from pathlib import Path
import json

from textual.app import App, ComposeResult
from textual.widgets import (
    Input,
    Button,
    Header,
    RichLog,
    SelectionList,
    Label,
)
from textual.containers import (
    Container,
    Horizontal,
    HorizontalScroll,
    Vertical,
    VerticalScroll,
)
from textual.validation import Length


class BidRunner:
    def __init__(self):
        self.aws_credentials_set = False
        self.aws_creds = {}
        self.runner_details = {}
        self.sqs_status = []
        self.task_status = []
        self.aws_creds_ok = False

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
            self.aws_creds_ok = True
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

    def run(self, task_definition):
        try:
            cluster_name = "WaterTrackerDevCluster"
            task_definition_family = "water-tracker-model-runs"
            task_definition_revision = "8"
            task_definition = f"{task_definition_family}:{task_definition_revision}"
            self.logger.write(f"running bid on cluster: {cluster_name}")

            ecs_client = boto3.client("ecs", region_name="us-west-2", **self.aws_creds)
            ecs_client.register_task_definition(**task_definition)
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
            )

            task_arn = resp["tasks"][0]["taskArn"]
            last_status = resp["tasks"][0]["lastStatus"]
            self.runner_details["cluster"] = cluster_name
            self.runner_details["tasks"] = [task_arn]

            self.logger.write(
                f"Task - running on cluster: {self.runner_details['cluster']}"
            )
            self.logger.write(f"the value of the dict\n{self.runner_details}")
            self.logger.write(f"Task - Arn: {self.runner_details['tasks']}")
            self.logger.write(f"Task - Status: {last_status}")
        except Exception as e:
            self.logger.write("An error occured trying to run the task")
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

    async def check_sqs_Q(self, queue_url):
        self.logger.write("[bold yellow]Retrieving Bid messages...[/bold yellow]")
        sqs_client = boto3.client("sqs", region_name="us-west-2", **self.aws_creds)
        try:
            response = await asyncio.to_thread(
                sqs_client.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=10,
            )
            messages = response.get("Messages", [])
            if messages:
                for message in messages:
                    self.sqs_status.append(message.get("Body"))
                    await asyncio.to_thread(
                        sqs_client.delete_message,
                        QueueUrl=queue_url,
                        ReceiptHandle=message["ReceiptHandle"],
                    )
            else:
                self.logger.write("[bold blue]No new messages.[/bold blue]")
        except Exception as e:
            self.logger.write(f"[bold red]Error retrieving messages: {e}[/bold red]")
        finally:
            self.logger.write(
                "[bold yellow]Finished retrieving messages.[/bold yellow]"
            )
            for msg in self.sqs_status:
                self.logger.write(f"[bold blue]Bid Status:[/bold blue] {msg}")
            self.sqs_status = []

    async def check_bid_status(self, q_url):
        if self.aws_creds_ok:
            self.check_task_status()
            await self.check_sqs_Q(q_url)

            if len(self.task_status) > 0:
                self.logger.write(
                    f"[bold magenta]Task - status:[/bold magenta] {self.task_status.pop()}"
                )
            else:
                self.logger.write("[bold magenta]Task - no new messages[/bold magenta]")
            if len(self.sqs_status) > 0:
                for message in self.sqs_status:
                    self.logger.write(f"[bold blue]Bid Status:[/bold blue] {message}")
                self.sqs_status = []
            else:
                self.logger.write("[bold blue]Bid - no new messages[/bold blue]")
        else:
            self.logger.write("Setup aws account credentials to check status.")

    def __repr__(self):
        return "<BidRunner Input>"


# App ---------------------------------------------------


class BidRunnerApp(App):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    CSS_PATH = os.path.join(current_dir, "resources", "styles.tcss")

    def on_mount(self) -> None:
        load_dotenv()
        self.title = "Bidrunner2"
        self.runner = BidRunner()
        self.runner.aws_set_credentials(
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("AWS_SESSION_TOKEN"),
        )
        self.notify("Welcome to bidrunner2!")

    def compose(self) -> ComposeResult:
        rl = RichLog(
            auto_scroll=True, highlight=True, markup=True, id="bid-run-logs", wrap=True
        )
        rl.border_title = "Run Logs"
        yield Header()
        yield HorizontalScroll(
            VerticalScroll(
                Input(
                    placeholder="Bid Name",
                    id="bid-name",
                    classes="input-focus input-element",
                ),
                Input(
                    placeholder="Input data bucket",
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
                Input(
                    placeholder="Output bucket",
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
                        "Check AWS Connection",
                        id="submit-aws-connection-check",
                        variant="default",
                    ),
                    Button(
                        "Check Task Status",
                        id="check-task-status",
                        variant="default",
                    ),
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

    def validate_inputs(self) -> None:
        input_ids = [
            "#bid-name",
            "#bid-input-bucket",
            "#bid-auction-id",
            "#bid-auction-shapefile",
            "#bid-split-id",
            "#bid-id",
            # "#bid-months",
            "#bid-waterfiles",
            "#bid-output-bucket",
        ]
        show_notification = False
        for id in input_ids:
            widget_element = self.query_one(id, Input)
            if not widget_element.value:
                show_notification = True
                widget_element.add_class("error")
            else:
                widget_element.remove_class("error")
        if show_notification:
            self.notify(
                "invalid form, please submit all required fields", severity="error"
            )

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
            bid_input_bucket = self.query_one("#bid-input-bucket", Input).value
            bid_auction_id = self.query_one("#bid-auction-id", Input).value
            bid_auction_shapefile = self.query_one(
                "#bid-auction-shapefile", Input
            ).value
            bid_split_id = self.query_one("#bid-split-id", Input).value
            bid_id = self.query_one("#bid-id", Input).value
            bid_months = self.query_one("#bid-months", SelectionList).selected
            bid_waterfiles = self.query_one("#bid-waterfiles", Input).value
            bid_output_bucket = self.query_one("#bid-output-bucket", Input).value

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
                selected_months,
                bid_waterfiles,
                bid_output_bucket,
            ]

            task_definition = self.runner.create_task_definition(all_inputs)

            self.validate_inputs()

            # self.runner.run()
            # log.write(f"CLUSTER: {self.runner.runner_details.get('cluster')}")
        if event.button.id == "check-task-status":
            queue_url = (
                "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"
            )
            await self.runner.check_bid_status(queue_url)
        if event.button.id == "clear-logs":
            log.clear()


def main():
    app = BidRunnerApp()
    app.run()


if __name__ == "__main__":
    main()
