.PHONY: upgrade

upgrade: ## Keep this for compatibility with the `upgrade-python-requirements` CI workflow
	pip install uv
	uv venv --allow-existing
	uv lock --upgrade
