FROM nikolaik/python-nodejs as base

# Copy over package deps
COPY server/Pipfile /app/server/
COPY server/Pipfile.lock /app/server/
COPY client/package.json /app/client/
COPY client/package-lock.json /app/client/

FROM base as installation
COPY Makefile /app

WORKDIR /app
RUN make install

# Copying this and building it first because it doesn't change as often
FROM installation as web
COPY client/ /app/client

WORKDIR /app
RUN make buildweb

# Then we copy over the server files and then move over the 
FROM web as server
COPY server/ /app/server

WORKDIR /app

EXPOSE 5111
EXPOSE 5555

ENTRYPOINT [ "make", "api" ]