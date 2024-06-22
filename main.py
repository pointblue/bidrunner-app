import boto3
from dotenv import load_dotenv
import os
from aiobotocore.session import get_session

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Input, Button, Header, SelectionList, Log, Label
from textual.containers import Container, Horizontal
from textual.events import Click
from textual.validation import Length


class BidRunner:
    def __init__(self, aws_credentials, logger: Log):
        self.aws_credentials_set = False
        self.logger = logger
        self.aws_creds = {}
        self.runner_details = {"cluster": None, "tasks": []}

    def aws_set_credentials(self, access_key, secret_key, session_token):
        self.aws_creds = {}
        self.aws_creds["aws_access_key_id"] = access_key
        self.aws_creds["aws_secret_access_key"] = secret_key
        self.aws_creds["aws_session_token"] = session_token

    def aws_check_credentials(self):
        try:
            self.logger.write_line("trying to connect to aws")
            s3 = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
            _ = s3.list_buckets()
            return True
        except Exception as e:
            self.logger.write_line(
                "unable to connect to aws, with the following error:"
            )
            self.logger.write_line(f"{e}")
            return False

    def run(self):
        try:
            cluster_name = "WaterTrackerDevCluster"
            task_definition_family = "water-tracker-model-runs"
            task_definition_revision = "8"
            task_definition = f"{task_definition_family}:{task_definition_revision}"
            self.logger.write_line(f"running bid on cluster: {cluster_name}")

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
            )

            task_arn = resp["tasks"][0]["taskArn"]
            last_status = resp["tasks"][0]["lastStatus"]
            self.runner_details["cluster"] = cluster_name
            self.runner_details["tasks"] = [task_arn]

            self.logger.write_line(
                f"Task - running on cluster: {self.runner_details['cluster']}"
            )
            self.logger.write_line(f"the value of the dict\n{self.runner_details}")
            self.logger.write_line(f"Task - Arn: {self.runner_details['tasks']}")
            self.logger.write_line(f"Task - Status: {last_status}")
        except Exception as e:
            self.logger.write_line("An error occured trying to run the task")
            self.logger.write_line(f"{e}")

    def check_task_status(self):
        if not self.runner_details.get("tasks") or not self.runner_details.get(
            "cluster"
        ):
            self.logger.write_line(
                f"invalid values for tasks and cluster, these are tasks={self.runner_details.get('tasks')} and cluster={self.runner_details.get('cluster')}"
            )
        else:
            cl = boto3.client("ecs", region_name="us-west-2", **self.aws_creds)
            res = cl.describe_tasks(**self.runner_details)
            task = res["tasks"][0]
            last_status = task["lastStatus"]
            self.logger.write_line(
                f"Task ARN: {self.runner_details['tasks'][0]} - Status: {last_status}"
            )

    def check_sqs_Q(self, queue_url, message_handler):
        sqs_client = boto3.client("sqs", region_name="us-west-2", **self.aws_creds)
        resp = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
        )
        messages = resp.get("Messages", [])
        for message in messages:
            self.logger.write_line(message["Body"])
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
            )

    def __repr__(self):
        return "<BidRunner Input>"


# App ---------------------------------------------------


class BidRunnerApp(App):
    CSS_PATH = "styles.tcss"

    def on_mount(self) -> None:
        load_dotenv()
        self.title = "Bidrunner2"
        log = self.query_one(Log)
        log.write_line("Welcome to Bidrunner2!")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Container(
                Input(
                    placeholder="Bid Name",
                    id="bid-name",
                    classes="input-focus",
                    validators=[Length(minimum=1)],
                    validate_on=["blur"],
                ),
                Input(
                    placeholder="Input data bucket",
                    id="bid-input-bucket",
                    classes="input-focus",
                    validators=[Length(minimum=1)],
                    validate_on=["blur"],
                ),
                Input(
                    placeholder="Auction Id",
                    id="bid-auction-id",
                    classes="input-focus",
                    validators=[Length(minimum=1)],
                    validate_on=["blur"],
                ),
                Input(placeholder="enter bid id", id="bid-id", classes="input-focus"),
                SelectionList[int](
                    ("January", 1, True),
                    ("February", 2),
                    ("March", 3),
                    ("April", 4),
                    ("May", 5),
                    ("June", 6),
                    id="bid-months",
                    classes="input-focus",
                ),
                Input(
                    placeholder="enter bid split id",
                    id="bid-split-id",
                    classes="input-focus",
                ),
                Label(id="validation_errors"),
                Horizontal(
                    Button(
                        "Submit",
                        id="submit_run",
                        variant="default",
                        classes="input-focus",
                    ),
                    Button(
                        "Check AWS Connection",
                        id="submit-aws-connection-check",
                        variant="warning",
                        classes="input-focus",
                    ),
                    Button(
                        "Check Task Status",
                        id="check-task-status",
                        variant="warning",
                        classes="input-focus",
                    ),
                ),
                id="main-ui",
            ),
            Container(Log(auto_scroll=True), id="log_ui"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one(Log)
        bid_input_bucket = self.query_one("#bid-input-bucket", Input).value
        runner = BidRunner(bid_input_bucket, log)
        runner.aws_set_credentials(
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("AWS_SESSION_TOKEN"),
        )
        if event.button.id == "submit-aws-connection-check":
            creds_ok = runner.aws_check_credentials()
            log.write_line(f"Connected to aws? {'Yes' if creds_ok else 'No'}")
        if event.button.id == "submit_run":
            log.write_line(f"Bid Submitted: {runner}")
            runner.run()
            # queue_url = (
            #     "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"
            # )
            log.write_line(f"CLUSTER: {runner.runner_details.get('cluster_name')}")
        if event.button.id == "check-task-status":
            runner.check_task_status()


# class A:
#     def __init__(self):
#         self.d = {}
#
#     def setup(self, a, b):
#         self.d["a"] = a
#         self.d["b"] = b
#
#     def use(self, add_this):
#         return self.d.get("a") + add_this
#
#     def print_d(self):
#         print(self.d)
#

if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
