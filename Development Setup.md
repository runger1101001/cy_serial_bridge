# Development Setup

This library uses Poetry to handle setting up for development and uploading the package to PyPi.

Note: Installing this library requires poetry >= 1.2.0. This is newer than what's included in Ubuntu 22.04, so on
that Ubuntu version and older, you will have to install poetry via pipx.

## Cheat Sheet

### Setting Up for Local Dev
```shell
poetry install --with=linters --with=tests
poetry shell # This activates a virtual environment containing the dependencies
```

### Running Linters and Formatter
```shell
poetry run mypy -p cy_serial_bridge
poetry run ruff check --fix .
poetry run ruff format .
```

### Running Tests
```shell
poetry run pytest -v --capture=no --log-cli-level=INFO tests/
```

### Uploading to PyPi
TODO