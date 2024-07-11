from setuptools import setup, find_packages

setup(
    name="bidrunner2",
    version="0.1",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "bidrunner2": ["resources/*"],
    },
    install_requires=[
        "boto3",
        "python-dotenv",
        "rich",
        "textual",
        "toml",
    ],
    entry_points={
        "console_scripts": [
            "bidrunner2=bidrunner2.main:main",
        ],
    },
)
