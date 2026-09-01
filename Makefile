.PHONY: test lint dev backend-test frontend-test

test: backend-test frontend-test

backend-test:
	cd backend && .venv/bin/python -m pytest

frontend-test:
	cd frontend && npm run test

lint:
	cd backend && .venv/bin/python -m compileall -q app tests
	cd frontend && npm run lint

dev:
	@echo "Start the backend in one terminal: cd backend && uvicorn app.main:app --reload"
	@echo "Start the frontend in another: cd frontend && npm run dev"
