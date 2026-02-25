from relaymd_api_client import client


def test_client_module_importable() -> None:
    assert client is not None
