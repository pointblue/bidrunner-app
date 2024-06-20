import boto3
from dotenv import load_dotenv
import os

from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Button, Header
from textual.containers import Vertical


class BidRunner:
    def __init__(self, s3_input, s3_output, template):
        self.s3_input = s3_input
        self.s3_output = s3_output

        load_dotenv()

        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        self._session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )
        self._s3_session = self._session.resource("s3")
        self._ec2_client = self._session.client("ec2")

    def ec2_create(self):
        self._ec2_client.launch_instances()

    def s3_verify(self):
        self._s3_session.create()


class BidRunnerApp(App):
    def on_mount(self) -> None:
        self.title = "Bidrunner 2"
        load_dotenv()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="enter bid id", id="bid-id")
        yield Input(placeholder="enter months", id="bid-months")
        yield Input(placeholder="enter bid split id", id="bid-split-id")
        yield Button("Submit", id="submit-run", variant="default")


if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
