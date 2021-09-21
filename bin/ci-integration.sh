#!/usr/bin/env bash

./bin/wait-for-it.sh -h deepquestai-deepstack -p 5000 -t 60

docker run --rm --name integration \
      --volume  "$(pwd)":"$(pwd)"    \
      --workdir "$(pwd)"             \
      --network=host                 \
      "${CI_IMAGE}" bash -c './bin/integration.sh'
