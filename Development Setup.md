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

### Running Formatter
```shell
poetry run ruff check --fix .
poetry run ruff format .
```

### Running Tests
```shell
poetry run pytest --capture=no tests/
```

### Uploading to PyPi
TODO