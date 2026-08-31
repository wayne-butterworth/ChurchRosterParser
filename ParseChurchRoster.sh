#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <input_pdf> <name>"
    echo "  Note: <name> should be exactly the same as in the roster."
    exit 1
fi

# run the parser
#python3 ParseChurchRoster.py -i "$1" -n "$2"
python3 ParseChurchRoster.py -i "$1" -n "Wayne B"   # since it's always me

# upload the .ics to my Google Calendar
# TODO: implement this 