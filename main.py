from logging import raiseExceptions
from sys import exception
import boto3
from dotenv import load_dotenv
import os
import time
import asyncio
import threading

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Input, Button, Header, SelectionList, Log, Label
from textual.containers import Container, Horizontal
from textual.events import Click
from textual.validation import Length


class BidRunner:
    def __init__(self, s3_input, logger: Log):
        self.s3_input = s3_input
        self.aws_is_connected = False
        self.logger = logger

    def aws_connect(self, access_key, secret_key, session_token):
        try:
            self.logger.write_line("trying to connect to aws")
            self.aws_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,
                region_name="us-west-2",
            )
            s3_client = self.aws_session.client("s3")
            buckets = s3_client.list_buckets()
            self.aws_is_connected = True
            self.logger.write_line("connected!")
        except Exception as e:
            self.logger.write_line(
                "unable to connect to aws, with the following error:"
            )
            self.logger.write_line(f"{e}")

    def run(self):
        self.logger.write_line("running bid on cluster")
        cluster_name = "WaterTrackerDevCluster"
        task_definition_family = "water-tracker-model-runs"
        task_definition_revision = "7"
        task_definition = f"{task_definition_family}:{task_definition_revision}"

        if not self.aws_is_connected:
            raise Exception("aws needs to be connected")

        cl = self.aws_session.client("ecs")
        resp = cl.run_task(
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

    def pollQ(self):
        sqs = self.aws_session.client("sqs")
        queue_url = "https://sqs.us-west-2.amazonaws.com/975050180415/water-tracker-Q"

        while True:
            try:
                response = sqs.receive_message(
                    QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=20
                )

                messages = response.get("Messages", [])

                if messages:
                    for message in messages:
                        body = message.get("Body", "")
                        self.logger.write_line(body)
                        receipt_handle = message["ReceiptHandle"]

                        sqs.delete_message(
                            QueueUrl=queue_url, ReceiptHandle=receipt_handle
                        )
                else:
                    self.logger.write_line("No messages received.")

            except Exception as e:
                self.logger.write_line(f"Error receiving messages: {str(e)}")

    def __repr__(self):
        return f"<BidRunner Input: {'aws connected' if self.aws_is_connected else 'aws NOT connected'}>"


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
                ),
                id="main-ui",
            ),
            Container(Log(), id="log_ui"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one(Log)
        bid_input_bucket = self.query_one("#bid-input-bucket", Input).value
        runner = BidRunner(bid_input_bucket, log)
        runner.aws_connect(
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("AWS_SESSION_TOKEN"),
        )
        if event.button.id == "submit-aws-connection-check":
            log.write_line(
                f"Connected to aws? {'Yes' if runner.aws_is_connected else 'No'}"
            )
        if event.button.id == "submit_run":
            log.write_line(f"Bid Submitted: {runner}")
            runner.run()
            poll_thread = threading.Thread(target=runner.pollQ)
            poll_thread.daemon = True
            poll_thread.start()


if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
