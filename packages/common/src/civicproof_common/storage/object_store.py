from __future__ import annotations

import io
from abc import ABC, abstractmethod

import boto3
from botocore.exceptions import ClientError

from civicproof_common.config import get_settings


class ObjectStore(ABC):
    @abstractmethod
    async def put_artifact(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
        ...

    @abstractmethod
    async def get_artifact(self, key: str) -> bytes:
        ...

    @abstractmethod
    async def artifact_exists(self, content_hash_value: str) -> bool:
        ...


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=self._bucket)

    async def put_artifact(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
        safe_meta = {k: str(v) for k, v in metadata.items()}
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=io.BytesIO(data),
            Metadata=safe_meta,
        )
        return key

    async def get_artifact(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    async def artifact_exists(self, content_hash_value: str) -> bool:
        prefix = f"artifacts/{content_hash_value[:2]}/{content_hash_value}"
        response = self._client.list_objects_v2(
            Bucket=self._bucket, Prefix=prefix, MaxKeys=1
        )
        return response.get("KeyCount", 0) > 0

    def storage_key(self, source: str, hash_value: str, suffix: str = ".raw") -> str:
        return f"artifacts/{hash_value[:2]}/{hash_value}/{source}{suffix}"


def build_object_store() -> S3ObjectStore:
    settings = get_settings()
    endpoint = None
    if settings.MINIO_ENDPOINT:
        scheme = "https" if settings.MINIO_USE_SSL else "http"
        endpoint = f"{scheme}://{settings.MINIO_ENDPOINT}"
    return S3ObjectStore(
        endpoint_url=endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        bucket=settings.MINIO_BUCKET,
    )
