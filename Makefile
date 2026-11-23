# SwiftPM 6.3's Swift Build passes -suppress-warnings to SetappResources.
SWIFT_6_3 = $(shell xcrun swift --version 2>/dev/null | grep -Eq 'Swift version 6\.3([[:space:].]|$$)' && printf yes)
SWIFT_FLAGS = --build-system swiftbuild -Xswiftc -strict-concurrency=complete $(if $(SWIFT_6_3),,-Xswiftc -warnings-as-errors)

.DEFAULT_GOAL := check
.PHONY: check check-distribution lint format test test-tools build-macos test-consumer

check: check-distribution test test-consumer

check-distribution: lint test-tools

lint:
	mise exec -- python3 -B tools/quality.py check

format:
	mise exec -- python3 -B tools/quality.py format

test:
	xcrun swift test $(SWIFT_FLAGS)

test-tools:
	python3 -B -m unittest discover -s tools/tests -v

build-macos:
	xcrun swift build --target SetappAccessMacOS $(SWIFT_FLAGS)

test-consumer:
	python3 -B tools/consumer.py $(if $(SWIFT_6_3),--allow-warnings)
