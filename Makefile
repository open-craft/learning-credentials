.PHONY: upgrade

upgrade: piptools ## Keep this for compatibility with the `upgrade-python-requirements` CI workflow
	uv venv --allow-existing
	uv lock --upgrade
