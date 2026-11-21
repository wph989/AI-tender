"""S3 就绪检查只探测 bucket，不读写业务对象。"""

from unittest.mock import Mock

from botocore.exceptions import ClientError

from tender.adapters.storage.s3 import S3BlobStore


def test_s3_health_checks_configured_bucket():
    client = Mock()
    store = S3BlobStore(
        endpoint_url="http://unused",
        bucket="fixture-bucket",
        access_key=None,
        secret_key=None,
        region="us-east-1",
        client=client,
    )

    assert store.health() is True
    client.head_bucket.assert_called_once_with(Bucket="fixture-bucket")

    client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "forbidden"}}, "HeadBucket",
    )
    assert store.health() is False
