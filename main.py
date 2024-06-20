import boto3
from dotenv import load_dotenv
import os

from textual.app import App, ComposeResult
from textual.widgets import (
    Input,
    Label,
    Button,
    Header,
    Select,
    SelectionList,
    ListView,
    ListItem,
)
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


# App ---------------------------------------------------


class MultiSelectList(ListView):
    def __init__(self, options):
        super().__init__()
        self.options = options
        self.selected = set()
        self.build_options()

    def build_options(self):
        for option in self.options:
            self.append(ListItem(option))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.node
        if item in self.selected:
            self.selected.remove(item)
            item.remove_class("selected")
        else:
            self.selected.add(item)
            item.add_class("selected")


class BidRunnerApp(App):
    CSS_PATH = "styles.tcss"

    def on_mount(self) -> None:
        self.title = "Bidrunner 2"
        load_dotenv()

    def compose(self) -> ComposeResult:
        BID_MONTHS = ["January", "February", "March", "April", "May", "June"]
        select_bid_months = ((line, line) for line in BID_MONTHS)
        yield Header()
        yield Input(placeholder="enter bid id", id="bid-id")
        yield SelectionList[int](
            ("Falken's Maze", 0, True),
            ("Black Jack", 1),
            ("Gin Rummy", 2),
            ("Hearts", 3),
            ("Bridge", 4),
            ("Checkers", 5),
            ("Chess", 6, True),
            ("Poker", 7),
            ("Fighter Combat", 8, True),
        )
        yield Input(placeholder="enter bid split id", id="bid-split-id")
        yield Button("Submit", id="submit-run", variant="default")


if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
