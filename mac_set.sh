#!/bin/bash
# MAC 设置脚本

INTERFACE=$1
NEW_MAC=$2

echo "Setting MAC: $NEW_MAC on $INTERFACE"

ip link set dev "$INTERFACE" down && \
ip link set dev "$INTERFACE" address "$NEW_MAC" && \
ip link set dev "$INTERFACE" up

if [ $? -eq 0 ]; then
    echo "Success: MAC set to $NEW_MAC"
    exit 0
else
    echo "Error: Failed to set MAC"
    exit 1
fi
