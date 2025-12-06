#!/bin/bash
# FE development loader.
# Loads up development env from a shell script, which is much more flexible than using make.

# May be required for nvm setup in this shell.
source ~/.bashrc

cd "$(dirname "$0")/../services/frontend"

nvm use

npm install

npm run dev -- --host
