#!/bin/bash

# Idealista Bot Runner - determines appropriate interval based on time

# Get current time in Spain (Europe/Madrid timezone)
SPAIN_HOUR=$(TZ='Europe/Madrid' date +%H)

# Spanish business hours: 8am-9pm (08:00-21:00)
if [ "$SPAIN_HOUR" -ge 8 ] && [ "$SPAIN_HOUR" -lt 21 ]; then
    INTERVAL="business"
else
    INTERVAL="off-hours"
fi

echo "$(date): Running bot - Spain time: ${SPAIN_HOUR}:00 - Mode: $INTERVAL" >> ~/idealista-bot/logs/scheduler.log

# Run the bot
cd ~/idealista-bot
/usr/bin/python3 idealista_bot.py
