.PHONY: up test down

up:
	docker compose up --build

test:
	docker compose run --rm --build api pytest

down:
	docker compose down
