import boto3
from dotenv import load_dotenv
import os
from rich.text import Text

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Input, Button, Header, RichLog, SelectionList, Log, Label
from textual.containers import Container, Horizontal
from textual.events import Click
from textual.validation import Length


class BidRunner:
    def __init__(self):
        self.aws_credentials_set = False
        self.aws_creds = {}
        self.runner_details = {}
        self.sqs_status = []
        self.task_status = []

    def set_logger(self, log: RichLog):
        self.logger = log

    def aws_set_credentials(self, access_key, secret_key, session_token):
        self.aws_creds = {}
        self.aws_creds["aws_access_key_id"] = access_key
        self.aws_creds["aws_secret_access_key"] = secret_key
        self.aws_creds["aws_session_token"] = session_token

    def aws_check_credentials(self):
        try:
            self.logger.write("trying to connect to aws")
            s3 = boto3.client("s3", **self.aws_creds, region_name="us-west-2")
            _ = s3.list_buckets()
            return True
        except Exception as e:
            self.logger.write("unable to connect to aws, with the following error:")
            self.logger.write(f"{e}")
            return False

    def run(self):
        try:
            cluster_name = "WaterTrackerDevCluster"
            task_definition_family = "water-tracker-model-runs"
            task_definition_revision = "8"
            task_definition = f"{task_definition_family}:{task_definition_revision}"
            self.logger.write(f"running bid on cluster: {cluster_name}")

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

            self.logger.write(
                f"Task - running on cluster: {self.runner_details['cluster']}"
            )
            self.logger.write(f"the value of the dict\n{self.runner_details}")
            self.logger.write(f"Task - Arn: {self.runner_details['tasks']}")
            self.logger.write(f"Task - Status: {last_status}")
        except Exception as e:
            self.logger.write("An error occured trying to run the task")
            self.logger.write(f"{e}")

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
            self.logger.write(
                f"Task ARN: {self.runner_details['tasks'][0]} - Status: {last_status}"
            )
            self.task_status.append(last_status)

    def check_sqs_Q(self, queue_url):
        sqs_client = boto3.client("sqs", region_name="us-west-2", **self.aws_creds)
        resp = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20
        )
        messages = resp.get("Messages", [])
        for message in messages:
            self.sqs_status.append(message.get("Body"))
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
            )

    def check_bid_status(self, q_url):
        self.check_task_status()
        self.check_sqs_Q(q_url)

        self.logger.write(
            f"[bold magenta]Task - status:[/bold magenta] {self.task_status.pop()}"
        )
        self.logger.write(
            f"[bold blue]Bid - status:[/bold blue] {self.sqs_status.pop()}"
        )

    def __repr__(self):
        return "<BidRunner Input>"


# App ---------------------------------------------------


class BidRunnerApp(App):
    CSS_PATH = "styles.tcss"

    def on_mount(self) -> None:
        load_dotenv()
        self.title = "Bidrunner2"
        log = self.query_one(RichLog)
        log.write("Welcome to Bidrunner2!")
        self.runner = BidRunner()
        self.runner.aws_set_credentials(
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("AWS_SESSION_TOKEN"),
        )

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
            Container(
                RichLog(auto_scroll=True, highlight=True, markup=True), id="log_ui"
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one(RichLog)
        self.runner.set_logger(log)
        if event.button.id == "submit-aws-connection-check":
            creds_ok = self.runner.aws_check_credentials()
            log.write(f"Connected to aws? {'Yes' if creds_ok else 'No'}")
        if event.button.id == "submit_run":
            self.runner.run()
            log.write(f"CLUSTER: {self.runner.runner_details.get('cluster')}")
        if event.button.id == "check-task-status":
            queue_url = (
                "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"
            )
            self.runner.check_bid_status(queue_url)


if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
