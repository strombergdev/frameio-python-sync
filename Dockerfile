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

FROM installation as run
COPY . /app

WORKDIR /app

RUN make buildweb

EXPOSE 5111
EXPOSE 5555

ENTRYPOINT [ "make", "api" ]