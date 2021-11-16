## Development, build and maintenance tasks

VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
all: .tox/log/recreate.log build

.PHONY: build
build: .tox/log/recreate.log
	.tox/build/bin/python -m build

.PHONY: format
format: .tox/log/recreate.log
	.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	.tox/lint/bin/black ./

.PHONY: test
test: .tox/log/recreate.log format
	tox

.PHONY: test-debug
test-debug: .tox/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
upgrade: .git/hooks/pre-commit .git/hooks/pre-push
	touch "./pyproject.toml"
	$(MAKE) "test"

.PHONY: clean
clean:
	git clean -dfx -e "var/"


## Real targets

requirements.txt: pyproject.toml setup.cfg tox.ini
	tox -r -e "build"

.tox/log/recreate.log: requirements.txt tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r --notest -v | tee "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
.tox/log/editable.log: .tox/log/recreate.log
	./.tox/py3/bin/pip install -e "./"

.git/hooks/pre-commit: .tox/log/recreate.log
	.tox/lint/bin/pre-commit install

.git/hooks/pre-push: .tox/log/recreate.log
	.tox/lint/bin/pre-commit install --hook-type pre-push
