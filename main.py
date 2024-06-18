import boto3
from dotenv import load_dotenv
import os

load_dotenv()


s3_input_bucket = ""
s3_output_bucket = ""


class BidRunner:
    def __init__(self, s3_input, s3_output):
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
        self._ec2_session = self._session.resource("ec2")

    def ec2_create(self):
        self._ec2_session.create()

    def s3_verify(self):
        self._s3_session.create()
