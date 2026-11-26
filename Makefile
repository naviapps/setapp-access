SDK_TOOLING ?= mise run sdk-tooling --

# SwiftPM 6.3's Swift Build passes -suppress-warnings to SetappResources.
SWIFT_6_3 = $(shell xcrun swift --version 2>/dev/null | grep -Eq 'Swift version 6\.3([[:space:].]|$$)' && printf yes)
SWIFT_FLAGS = --build-system swiftbuild -Xswiftc -strict-concurrency=complete $(if $(SWIFT_6_3),,-Xswiftc -warnings-as-errors)

.DEFAULT_GOAL := check
.PHONY: check check-source lint format test test-consumer-isolation build-macos test-consumer clean

check: check-source test test-consumer

check-source: lint test-consumer-isolation

lint:
	$(SDK_TOOLING) quality check

format:
	$(SDK_TOOLING) quality format

test:
	xcrun swift test $(SWIFT_FLAGS)

test-consumer-isolation:
	python3 -B -m unittest discover -s fixtures/consumers/swift -v

build-macos:
	xcrun swift build --target SetappAccessMacOS $(SWIFT_FLAGS)

clean:
	$(SDK_TOOLING) clean .build fixtures/consumers/swift/.build \
	  fixtures/acceptance/macos/setapp-link/.build

test-consumer: test-consumer-isolation
	$(SDK_TOOLING) swift-consumer $(if $(SWIFT_6_3),--allow-warnings)
