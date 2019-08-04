#!/bin/sh
inter=5 # 1min
while true
do
  isAliveProc=`ps ax | grep "shareable_ws_signaling_serv.py" | egrep -v "grep" | wc -l`
  if [ $isAliveProc -ge 1 ]; then 
    echo "target process alive."
  else
    echo "process has dead. do restart."
    python shareable_ws_signaling_serv.py --secure --port 11985 &>> sigserv_out.txt &
  fi
  sleep $inter # check interval
done
