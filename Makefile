#!/bin/sh

install:
	# Install CircleCI tooling
	curl -fLSs https://raw.githubusercontent.com/CircleCI-Public/circleci-cli/master/install.sh | bash
	# Install python packages
	cd server && pipenv install
	# Install NPM dependencies
	cd client && npm install

api:
	# Start API server
	cd server && pipenv run python main.py

web:
	# Start webpack server
	cd client && npm run serve

buildweb:
	# Build  Vue app and copy into server dir
	cd client && npm run build
