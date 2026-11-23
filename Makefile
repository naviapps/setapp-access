SWIFT_FLAGS := -Xswiftc -strict-concurrency=complete -Xswiftc -warnings-as-errors

.DEFAULT_GOAL := check
.PHONY: check check-distribution lint format test test-tools build-macos test-consumer

check: check-distribution test test-consumer

check-distribution: lint test-tools

lint:
	mise exec -- python3 -B tools/quality.py check

format:
	mise exec -- python3 -B tools/quality.py format

test:
	swift test $(SWIFT_FLAGS)

test-tools:
	python3 -B -m unittest discover -s tools/tests -v

build-macos:
	swift build --target SetappAccessMacOS $(SWIFT_FLAGS)

test-consumer:
	python3 -B tools/consumer.py
