from setuptools import setup, find_packages

setup(
    name="bidrunner2",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "boto3",
        "python-dotenv",
        "rich",
        "textual",
    ],
    entry_points={
        "console_scripts": [
            "bidrunner2=bidrunner2.main:main",
        ],
    },
)
