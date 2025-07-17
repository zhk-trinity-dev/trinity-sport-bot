#!/bin/sh

cd /opt/trinity-sport-bot/

git pull origin main

rm -rf .venv
python3 -m venv .venv
pip3 install -r requirements.txt

rm -f .env && touch .env
echo BOT_TOKEN=$BOT_TOKEN >> .env
echo GROUP_ID=$GROUP_ID >> .env
echo THREAD_ID=$THREAD_ID >> .env
echo OWNER_ID=$OWNER_ID >> .env

systemctl restart trinity-sport-bot.service
