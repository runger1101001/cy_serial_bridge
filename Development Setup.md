# Development Setup

This library uses Poetry to handle setting up for development and uploading the package to PyPi.

## Cheat Sheet

### Setting Up for Local Dev
```
python -m poetry install --with=linters
python -m poetry shell # This activates a virtual environment containing the dependencies
```

### Running Formatter
```
python -m poetry run ruff check --fix .
```

### Running Tests
```
python -m mypy . # Checks types

# Linux only, allows the loopback tests to pass
sudo ip route add 239.2.2.0/24 dev lo
sudo ip -6 route add table local ff11::/16 dev lo

python -m pytest . # Checks actual code
```

### Uploading to PyPi
TODO