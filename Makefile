#!/bin/sh

install:
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

build-docker:
	# Build the Docker container
	docker build . -t fio-sync:latest

run-docker:
	# Run the Docker container
	CLIENT_ID='<YOUR CLIENT ID>' docker run -it -v $PWD/data:/app/server/db -p 5111:5111 fio-sync:latest
