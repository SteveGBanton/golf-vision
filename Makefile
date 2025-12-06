.PHONY: be fe

be:
	@chmod 755 scripts/run-backend.sh
	./scripts/run-backend.sh

fe:
	@chmod 755 scripts/run-frontend.sh
	./scripts/run-frontend.sh
