import os
import tempfile
import zipfile
from pathlib import Path
from typing import Union

import boto3
from loguru import logger

from second_brain.config import settings


class S3Client:
    def __init__(
        self, bucket_name: str, region: str = settings.AWS_DEFAULT_REGION
    ) -> None:
        """Initialize S3 client and bucket name.

        Args:
            bucket_name: Name of the S3 bucket
            region: AWS region (defaults to AWS_DEFAULT_REGION or AWS_REGION env var, or 'us-east-1')
        """
        self.region = region
        self.s3_client = boto3.client("s3", region_name=self.region)
        self.bucket_name = bucket_name

    def upload_folder(self, local_path: Union[str, Path], s3_prefix: str = "") -> None:
        """
        Upload a local folder as a zip file to S3.

        Args:
            local_path: Path to the local folder
            s3_prefix: Optional prefix (folder path) in S3 bucket
        """
        # Ensure bucket exists before proceeding
        self.__create_bucket_if_doesnt_exist()

        local_path = Path(local_path)

        if not local_path.exists():
            raise FileNotFoundError(f"Local path does not exist: {local_path}")

        if not local_path.is_dir():
            raise NotADirectoryError(f"Local path is not a directory: {local_path}")

        # Create a temporary zip file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Walk through all files in the directory
                for root, _, files in os.walk(local_path):
                    for filename in files:
                        file_path = Path(root) / filename
                        # Add file to zip with relative path
                        zipf.write(file_path, file_path.relative_to(local_path))

            # Construct S3 key with prefix
            zip_filename = f"{local_path.name}.zip"
            s3_key = f"{s3_prefix.rstrip('/')}/{zip_filename}".lstrip("/")

            # Upload zip file
            logger.debug(
                f"Uploading {local_path} to {self.bucket_name} with key {s3_key}"
            )
            self.s3_client.upload_file(temp_zip.name, self.bucket_name, s3_key)

        # Clean up temporary zip file
        os.unlink(temp_zip.name)

    def __create_bucket_if_doesnt_exist(self) -> None:
        """
        Check if bucket exists and create it if it doesn't.
        Raises permission-related exceptions if user lacks necessary permissions.
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except self.s3_client.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                try:
                    self.s3_client.create_bucket(
                        Bucket=self.bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": self.region},
                    )
                except self.s3_client.exceptions.ClientError as create_error:
                    raise Exception(
                        f"Failed to create bucket {self.bucket_name}: {str(create_error)}"
                    )
            elif error_code == "403":
                raise Exception(f"No permission to access bucket {self.bucket_name}")
            else:
                raise

    def download_folder(self, s3_prefix: str, local_path: Union[str, Path]) -> None:
        """
        Download a zipped folder from S3 and extract it to local storage.

        Args:
            s3_prefix: Prefix (folder path) in S3 bucket
            local_path: Local path where files should be extracted
        """
        local_path = Path(local_path)

        # Create a temporary file to store the zip
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
            # Download the zip file
            self.s3_client.download_file(
                self.bucket_name,
                s3_prefix,  # Assuming s3_prefix now points directly to the zip file
                temp_zip.name,
            )

            # Create local directory if it doesn't exist
            local_path.mkdir(parents=True, exist_ok=True)

            # Extract the zip file
            with zipfile.ZipFile(temp_zip.name, "r") as zipf:
                zipf.extractall(local_path)

        # Clean up temporary zip file
        os.unlink(temp_zip.name)
