def test_package_can_be_imported() -> None:
    import procurepilot

    assert procurepilot.__name__ == "procurepilot"
