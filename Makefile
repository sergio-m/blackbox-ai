# Convenience wrappers around docker compose (see README.md).
TASK ?= Write a Python program that prints the first 10 prime numbers.
Q ?= Why did the coder change its solution?

.PHONY: build up run ask test down reset

.env:
	cp .env.example .env

build: .env
	docker compose build

up: .env
	docker compose up -d relate

run: .env
	docker compose run --rm agents run "$(TASK)"

ask: .env
	docker compose run --rm agents ask $(if $(RUN),--run $(RUN)) "$(Q)"

test: .env
	docker compose run --rm --no-deps --entrypoint python agents -m pytest -q

down:
	docker compose down

reset:
	docker compose down -v
