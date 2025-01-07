.PHONY: build up down logs test lint format

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	docker-compose run --rm api pytest

lint:
	docker-compose run --rm api flake8 .
	docker-compose run --rm api black . --check

format:
	docker-compose run --rm api black .
