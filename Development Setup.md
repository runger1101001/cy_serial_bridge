# Development Setup

This library uses Poetry to handle setting up for development and uploading the package to PyPi.

## Cheat Sheet

### Setting Up for Local Dev
```shell
poetry install --with=linters --with=tests
poetry shell # This activates a virtual environment containing the dependencies
```

### Running Formatter
```shell
poetry run ruff check --fix src
poetry run ruff format .
```

### Running Tests
```shell
poetry run pytest --capture=no tests/
```

### Uploading to PyPi
TODO