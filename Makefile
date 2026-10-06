.PHONY: up test down

up:
	docker compose up --build

test:
	docker compose run --rm api pytest

down:
	docker compose down
