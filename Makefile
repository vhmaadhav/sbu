.PHONY: frontend backend pet backend-test backend-smoke docker-up docker-down docker-logs docker-android

frontend:
	@./scripts/run-frontend

backend:
	@command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
	@cd backend && uv run --python 3.12 python -m study_buddy

pet:
	@command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
	@cd backend && uv run --python 3.12 python -m pet

backend-test:
	@cd backend && uv run --python 3.12 python -m unittest discover -s tests

backend-smoke:
	@cd backend && uv run --python 3.12 python scripts/smoke.py

docker-up:
	@docker compose --env-file .env.docker up --build -d

docker-down:
	@docker compose --env-file .env.docker down

docker-logs:
	@docker compose --env-file .env.docker logs -f

docker-android:
	@mkdir -p dist/android
	@docker compose --env-file .env.docker --profile tools run --rm android-build

