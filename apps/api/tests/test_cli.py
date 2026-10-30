from unittest.mock import patch

import pytest
from sales_manager_api.__main__ import main


def test_cli_passes_loopback_and_disables_access_logs():
    with patch("sales_manager_api.__main__.uvicorn.run") as run:
        main(["--port", "8123"])
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8123
    assert run.call_args.kwargs["access_log"] is False


@pytest.mark.parametrize("value", ["0", "65536", "invalid"])
def test_invalid_port_fails_before_starting_server(value):
    with patch("sales_manager_api.__main__.uvicorn.run") as run:
        with pytest.raises(SystemExit) as error:
            main(["--port", value])
        assert error.value.code == 2
        run.assert_not_called()


def test_bad_settings_exit_without_echoing_values(tmp_path, capsys):
    path = tmp_path / "bad.env"
    path.write_text("APP_ENV=private-marker\n")
    with patch("sales_manager_api.__main__.uvicorn.run") as run:
        with pytest.raises(SystemExit) as error:
            main(["--env-file", str(path)])
        assert error.value.code == 2
        run.assert_not_called()
    assert "private-marker" not in capsys.readouterr().err
