import leond


def test_package_exposes_version() -> None:
    assert leond.__version__ == "0.1.0"
