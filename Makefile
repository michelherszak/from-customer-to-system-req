.PHONY: up dev down test verify backup migrate seed health locks
up:
	./kusys up
dev:
	./kusys dev
down:
	./kusys down
test:
	./kusys test
verify:
	./kusys verify
backup:
	./kusys backup
migrate:
	./kusys migrate
seed:
	./kusys seed
health:
	./kusys health
locks:
	./kusys locks
