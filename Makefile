SWIFT_FLAGS := -Xswiftc -strict-concurrency=complete -Xswiftc -warnings-as-errors

.DEFAULT_GOAL := check
.PHONY: check lint format test test-tools build-macos test-consumer

check: lint test-tools test test-consumer

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
