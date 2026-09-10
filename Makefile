# Maubot plugin build & upload.
#
# Config via environment (or `make VAR=value`):
#   MAUBOT_URL     maubot admin base URL (default: https://maubot.local.awesome-it.de)
#   MAUBOT_TOKEN   admin access token (required for any upload target)
#   MBC / CURL     override tool binaries

MAUBOT_URL   ?= https://maubot.local.awesome-it.de
MAUBOT_TOKEN ?=
MBC          ?= mbc
CURL         ?= curl

PROD_ID     := de.awesome-it.maubot-alerts
TEST_ID     := de.awesome-it.maubot-alerts-test
PROD_MODULE := alertbot
TEST_MODULE := alertbot_test
VERSION     := $(shell awk '/^version:/ {print $$2}' maubot.yaml)

PROD_MBP := $(PROD_ID)-v$(VERSION).mbp
TEST_MBP := $(TEST_ID)-v$(VERSION).mbp

BUILD_TEST_DIR := .build-test

UPLOAD_URL := $(MAUBOT_URL)/_matrix/maubot/v1/plugins/upload?allow_override=true

.PHONY: help build build-test upload upload-test build-upload build-upload-test clean

help:
	@echo "Targets:"
	@echo "  build              build $(PROD_MBP)"
	@echo "  build-test         build $(TEST_MBP) (id temporarily swapped in maubot.yaml)"
	@echo "  upload             POST $(PROD_MBP) to $(MAUBOT_URL) via curl"
	@echo "  upload-test        POST $(TEST_MBP) to $(MAUBOT_URL) via curl"
	@echo "  build-upload       build then upload prod"
	@echo "  build-upload-test  build then upload test"
	@echo "  clean              remove *.mbp"
	@echo ""
	@echo "Env:"
	@echo "  MAUBOT_URL    ($(MAUBOT_URL))"
	@echo "  MAUBOT_TOKEN  (required for upload*)"

build: $(PROD_MBP)

# Always rebuild: mbc reads current sources; a stale .mbp is exactly what the
# user is trying to avoid by not using `mbc upload`.
$(PROD_MBP): FORCE
	rm -f $(PROD_MBP)
	$(MBC) build

# Test build: prod and test can't share the Python module name `alertbot` at
# runtime (maubot loads both into sys.modules, the second collides with the
# first). So we copy sources to a scratch dir, rename the module directory,
# rewrite absolute imports and maubot.yaml, then build there. Trap ensures
# the scratch dir is removed even on failure/interrupt.
build-test: FORCE
	rm -f $(TEST_MBP)
	rm -rf $(BUILD_TEST_DIR)
	@trap 'rm -rf $(BUILD_TEST_DIR)' EXIT INT TERM; \
	 mkdir -p $(BUILD_TEST_DIR) && \
	 cp -r maubot.yaml base-config.yaml $(PROD_MODULE) $(BUILD_TEST_DIR)/ && \
	 find $(BUILD_TEST_DIR) -type d -name __pycache__ -exec rm -rf {} + && \
	 mv $(BUILD_TEST_DIR)/$(PROD_MODULE) $(BUILD_TEST_DIR)/$(TEST_MODULE) && \
	 find $(BUILD_TEST_DIR)/$(TEST_MODULE) -name '*.py' -exec sed -i \
	     -e 's/^import $(PROD_MODULE)$$/import $(TEST_MODULE)/' \
	     -e 's/^import $(PROD_MODULE)\./import $(TEST_MODULE)./' \
	     -e 's/^from $(PROD_MODULE)\./from $(TEST_MODULE)./' \
	     -e 's/^from $(PROD_MODULE) import/from $(TEST_MODULE) import/' \
	     {} + && \
	 sed -i \
	     -e 's|^id: $(PROD_ID)$$|id: $(TEST_ID)|' \
	     -e 's|^  - $(PROD_MODULE)$$|  - $(TEST_MODULE)|' \
	     -e 's|$(PROD_MODULE)/templates/|$(TEST_MODULE)/templates/|g' \
	     $(BUILD_TEST_DIR)/maubot.yaml && \
	 (cd $(BUILD_TEST_DIR) && $(MBC) build) && \
	 mv $(BUILD_TEST_DIR)/$(TEST_MBP) .

# -L follows 3xx (e.g. http→https at the ingress). --fail-with-body still
# treats 4xx/5xx as errors so make sees the failure; without it curl -f
# swallows the response body on error, which is worse than useless.
# -w '%{http_code}' + a final grep asserts we ended on 2xx after redirects —
# curl -f doesn't error on 3xx, so we'd otherwise "succeed" without uploading.
upload: $(PROD_MBP)
	@test -n "$(MAUBOT_TOKEN)" || { echo "MAUBOT_TOKEN not set" >&2; exit 1; }
	@code=$$($(CURL) -sS -L --fail-with-body -o /dev/stderr -w '%{http_code}' \
	    -H "Authorization: Bearer $(MAUBOT_TOKEN)" \
	    -H "Content-Type: application/zip" \
	    --data-binary "@$(PROD_MBP)" \
	    -X POST "$(UPLOAD_URL)"); \
	 echo; \
	 case "$$code" in 2*) echo "uploaded $(PROD_MBP) (HTTP $$code)";; \
	   *) echo "upload failed (HTTP $$code)" >&2; exit 1;; esac

upload-test:
	@test -n "$(MAUBOT_TOKEN)" || { echo "MAUBOT_TOKEN not set" >&2; exit 1; }
	@test -f $(TEST_MBP) || { echo "$(TEST_MBP) missing; run 'make build-test' first" >&2; exit 1; }
	@code=$$($(CURL) -sS -L --fail-with-body -o /dev/stderr -w '%{http_code}' \
	    -H "Authorization: Bearer $(MAUBOT_TOKEN)" \
	    -H "Content-Type: application/zip" \
	    --data-binary "@$(TEST_MBP)" \
	    -X POST "$(UPLOAD_URL)"); \
	 echo; \
	 case "$$code" in 2*) echo "uploaded $(TEST_MBP) (HTTP $$code)";; \
	   *) echo "upload failed (HTTP $$code)" >&2; exit 1;; esac

build-upload: build upload

build-upload-test: build-test upload-test

clean:
	rm -f *.mbp
	rm -rf $(BUILD_TEST_DIR)

FORCE:
.PHONY: FORCE
