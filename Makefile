# Requiere GNU Make, Python >=3.11 y Docker Compose v2 con motor Linux.
PYTHON ?= python3
PG_PORT ?= 55432
export PG_PORT
ifeq ($(OS),Windows_NT)
VENV_PYTHON := .venv/Scripts/python.exe
else
VENV_PYTHON := .venv/bin/python
endif

.PHONY: setup up run stream test down clean verificar clients
setup:
	@"$(PYTHON)" tools/manage.py setup

up:
	@"$(VENV_PYTHON)" tools/manage.py prepare
	@"$(VENV_PYTHON)" tools/manage.py up

# El pipeline completo S03-S04 sigue pendiente; clients ejecuta únicamente S02.
run:
	@"$(VENV_PYTHON)" tools/manage.py run

clients:
	@"$(VENV_PYTHON)" -m src.clients

stream:
	@"$(VENV_PYTHON)" tools/manage.py stream

test:
	@"$(VENV_PYTHON)" -m unittest discover -s tests -v

down:
	@"$(VENV_PYTHON)" tools/manage.py down

# No borrar volúmenes por defecto; se definirá su limpieza en S07.
clean:
	@"$(VENV_PYTHON)" tools/manage.py clean

verificar:
	@"$(VENV_PYTHON)" tools/verificar_entrega.py
