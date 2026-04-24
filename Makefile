dev:
	docker compose up --build

test:
	docker compose run --rm backend pytest

migrate:
	docker compose run --rm backend alembic upgrade head

shell:
	docker compose run --rm backend bash

seed:
	docker compose run --build --rm backend python scripts/seed_data.py

test-e2e:
	docker compose run --rm backend pytest tests/test_e2e_pipeline.py -v -s
