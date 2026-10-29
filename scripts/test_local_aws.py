"""Check that local verification cannot fall back to remote AWS credentials/URLs."""

import os
import unittest
from unittest.mock import patch

from verify_local_aws import local_client, local_endpoint, local_session, run_checks


class LocalBoundaryTests(unittest.TestCase):
    def test_remote_or_ambiguous_endpoints_fail_before_creating_clients(self):
        rejected = [
            "",
            "https://dynamodb.ap-northeast-1.amazonaws.com",
            "http://127.0.0.1:4566.evil.invalid",
            "http://localhost:80",
            "http://user:password@localhost:4566",
            "http://localhost:4566/path",
            "http://localhost:4566?endpoint=remote",
            "http://0.0.0.0:4566",
            "http://localhost:4566//",
            "http://localhost:4566#fragment",
        ]
        with patch("verify_local_aws.boto3.Session") as session:
            for endpoint in rejected:
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    run_checks(endpoint)
            session.assert_not_called()

    def test_lifecycle_rejects_the_comparison_server_before_creating_clients(self):
        with patch("verify_local_aws.boto3.Session") as session:
            with self.assertRaises(ValueError):
                run_checks("http://127.0.0.1:4567", lifecycle=True)
            session.assert_not_called()

    def test_local_clients_ignore_profiles_endpoint_overrides_and_proxy(self):
        inherited = {
            "AWS_PROFILE": "nonexistent-personal-profile",
            "AWS_DEFAULT_PROFILE": "another-nonexistent-profile",
            "AWS_CONFIG_FILE": "/nonexistent-local-check-config",
            "AWS_SHARED_CREDENTIALS_FILE": "/nonexistent-local-check-credentials",
            "AWS_ACCESS_KEY_ID": "inherited-must-not-be-used",
            "AWS_SECRET_ACCESS_KEY": "inherited-must-not-be-used",
            "AWS_SESSION_TOKEN": "inherited-must-not-be-used",
            "AWS_ENDPOINT_URL": "https://remote.invalid",
            "AWS_ENDPOINT_URL_S3": "https://service-specific-remote.invalid",
            "HTTPS_PROXY": "https://proxy.invalid",
        }
        with patch.dict(os.environ, inherited):
            session = local_session()
            credentials = session.get_credentials().get_frozen_credentials()
            self.assertEqual(credentials.access_key, "test")
            self.assertEqual(credentials.secret_key, "test")
            self.assertFalse(credentials.token)
            client = local_client(session, "s3", "http://127.0.0.1:4566/")
            self.assertEqual(client.meta.endpoint_url, "http://127.0.0.1:4566")
            self.assertEqual(client.meta.region_name, "ap-northeast-1")
            self.assertEqual(client.meta.config.proxies, {})
            self.assertEqual(client.meta.config.s3["addressing_style"], "path")
            client.close()

    def test_known_loopback_urls_are_accepted(self):
        for endpoint in ("http://127.0.0.1:4566/", "http://localhost:4567"):
            self.assertEqual(local_endpoint(endpoint), endpoint.removesuffix("/"))


if __name__ == "__main__":
    unittest.main()
