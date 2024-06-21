from sys import exception
import boto3
from dotenv import load_dotenv
import os

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Input, Button, Header, Pretty, SelectionList, Log
from textual.containers import Container, Horizontal
from textual.events import Click
from textual.validation import Length


class BidRunner:
    def __init__(self, s3_input):
        self.s3_input = s3_input
        self.aws_is_connected = False

    def aws_connect(self, access_key, secret_key, session_token):
        try:
            self.aws_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,
            )
            self.aws_is_connected = True
        except Exception as e:
            print(e)

    def __repr__(self):
        return f"<BidRunner Input: {'aws connected' if self.aws_is_connected else 'aws NOT connected'}>"


# App ---------------------------------------------------


class BidRunnerApp(App):
    CSS_PATH = "styles.tcss"

    def on_mount(self) -> None:
        load_dotenv()
        self.title = "Bidrunner2"

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
                Pretty([]),
                Button(
                    "Submit", id="submit_run", variant="default", classes="input-focus"
                ),
                id="main-ui",
            ),
            Container(Log(), id="log_ui"),
        )

    # @on(Input.Changed)
    # def show_invalid_reasons(self, event: Input.Changed) -> None:
    #     # Updating the UI to show the reasons why validation failed
    #     if not event.validation_result.:
    #         self.query_one(Pretty).update(event.validation_result.failure_descriptions)
    #     else:
    #         self.query_one(Pretty).update([])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one(Log)
        bid_input_bucket = self.query_one("#bid-input-bucket", Input).value
        run = BidRunner(bid_input_bucket)
        run.aws_connect(
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_KEY"),
            os.getenv("AWS_SESSION_TOKEN"),
        )
        if event.button.id == "submit_run":
            log.write_line(f"Bid Submitted: {run}")


if __name__ == "__main__":
    app = BidRunnerApp()
    app.run()
