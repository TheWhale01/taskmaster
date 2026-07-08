# Taskmaster

This project is about job control. It's made in Python.

## How to setup 

### Nix:

```bash
nix develop .
nix run .#server -- config.yaml
nix run .#client
```

### Other distributions

> __*NOTE:*__ Please ensure that Python >=3.14 is installed

```bash
uv run server config.yaml
uv run client
```
